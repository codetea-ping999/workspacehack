from ws import cli


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
    assert "no repositories matched" in capsys.readouterr().err


def test_missing_config(tmp_path, capsys):
    assert cli.main(["status", "-c", str(tmp_path / "x.toml")]) == 2


def test_status_not_cloned(tmp_path, capsys):
    assert cli.main(["status", "-c", write_cfg(tmp_path)]) == 0
    assert "not cloned" in capsys.readouterr().out


def test_run_requires_command(tmp_path, capsys):
    assert cli.main(["run", "-c", write_cfg(tmp_path)]) == 2
