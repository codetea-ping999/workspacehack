import pytest

from ws import cli, dash, gitops, shell


def write_cfg(tmp_path, body=""):
    f = tmp_path / "repos.toml"
    f.write_text(f'root = "{tmp_path / "ws"}"\n[[repo]]\nname = "o/a"\ntags = ["x"]\n[[repo]]\nname = "o/b"\n{body}')
    return str(f)


def test_list_and_filters(tmp_path, capsys):
    cfg = write_cfg(tmp_path)
    assert cli.main(["list", "-c", cfg, "-t", "x"]) == 0
    out = capsys.readouterr().out
    assert "o/a" in out and "o/b" not in out


def test_no_match_is_error(tmp_path, capsys):
    assert cli.main(["list", "-c", write_cfg(tmp_path), "-r", "nope"]) == 2
    assert "matches no configured" in capsys.readouterr().err


def test_no_tag_match_is_error(tmp_path, capsys):
    assert cli.main(["list", "-c", write_cfg(tmp_path), "-t", "nothing"]) == 2
    assert "no repositories matched" in capsys.readouterr().err


def test_missing_config(tmp_path, capsys):
    assert cli.main(["status", "-c", str(tmp_path / "x.toml")]) == 2


def test_status_not_cloned(tmp_path, capsys):
    assert cli.main(["status", "-c", write_cfg(tmp_path)]) == 0
    assert "not cloned" in capsys.readouterr().out


def test_run_requires_command(tmp_path, capsys):
    assert cli.main(["run", "-c", write_cfg(tmp_path)]) == 2


def test_run_strips_only_the_leading_separator(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(gitops, "run_in", lambda repo, cmd: (seen.append(list(cmd)) or (0, "")))
    cfg = write_cfg(tmp_path)
    assert cli.main(["run", "-c", cfg, "-r", "o/a", "--", "git", "checkout", "--", "file.txt"]) == 0
    assert seen == [["git", "checkout", "--", "file.txt"]]
    seen.clear()
    assert cli.main(["run", "-c", cfg, "-r", "o/a", "--", "echo", "--", "--"]) == 0
    assert seen == [["echo", "--", "--"]]


def test_dash_creates_output_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(dash, "fetch", lambda name, pr_ci=True: dash.RepoReport(name))
    out = tmp_path / "reports" / "nested" / "dashboard.md"
    assert cli.main(["dash", "-c", write_cfg(tmp_path), "-o", str(out)]) == 0
    assert out.read_text().startswith("# Repository dashboard")


def test_dash_flags_are_passed_through(tmp_path, monkeypatch, capsys):
    seen = {}
    monkeypatch.setattr(dash, "fetch", lambda name, pr_ci=True: (seen.setdefault("pr_ci", pr_ci), dash.RepoReport(name, private=True))[1])
    assert cli.main(["dash", "-c", write_cfg(tmp_path), "--no-pr-ci", "--anonymize-private"]) == 0
    out = capsys.readouterr().out
    assert seen["pr_ci"] is False and "o/a" not in out and "2 private repos" in out


def test_init_creates_parent_dir_and_skips_forks(tmp_path, monkeypatch):
    def api(path, paginate=False):
        if path == "user":
            return {"login": "me"}
        return [{"full_name": "me/keep", "archived": False, "fork": False},
                {"full_name": "me/old", "archived": True, "fork": False},
                {"full_name": "me/forked", "archived": False, "fork": True}]
    monkeypatch.setattr(shell, "gh_api", api)
    out = tmp_path / "sub" / "repos.toml"
    assert cli.main(["init", "-o", str(out)]) == 0
    text = out.read_text()
    assert "me/keep" in text and "me/old" not in text and "me/forked" not in text


def test_init_org_fallback_only_on_404(tmp_path, monkeypatch, capsys):
    def make_api(err):
        def api(path, paginate=False):
            if path == "user":
                return {"login": "me"}
            if path.startswith("orgs/"):
                raise shell.CommandError(["gh"], 1, err)
            return [{"full_name": "bob/pub", "archived": False, "fork": False}]
        return api

    monkeypatch.setattr(shell, "gh_api", make_api("gh: Not Found (HTTP 404)"))
    assert cli.main(["init", "--owner", "bob", "-o", "-"]) == 0
    captured = capsys.readouterr()
    assert "bob/pub" in captured.out and "public repos only" in captured.err

    monkeypatch.setattr(shell, "gh_api", make_api("gh: API rate limit exceeded (HTTP 403)"))
    assert cli.main(["init", "--owner", "bob", "-o", "-"]) == 1


def test_status_fetch_flag(tmp_path, monkeypatch, capsys):
    fetched = []
    monkeypatch.setattr(gitops, "fetch", lambda repo: (fetched.append(repo.name) or ""))
    cfg = write_cfg(tmp_path)
    cli.main(["status", "-c", cfg, "--fetch"])
    assert sorted(fetched) == ["o/a", "o/b"]
    fetched.clear()
    cli.main(["status", "-c", cfg])
    assert fetched == [] and "ws status --fetch" in capsys.readouterr().out
