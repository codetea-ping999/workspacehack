from datetime import datetime, timezone

from ws import dash, shell

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)


def test_ci_state():
    assert dash.ci_state(None) == "-"
    assert dash.ci_state([{"status": "completed", "conclusion": "success"}]) == "✅"
    assert dash.ci_state([{"status": "completed", "conclusion": "success"}, {"status": "in_progress"}]) == "⏳"
    assert dash.ci_state([{"status": "completed", "conclusion": "failure"}, {"status": "in_progress"}]) == "❌"
    assert dash.ci_state([], [{"state": "success"}]) == "✅"
    assert dash.ci_state([], [{"state": "failure"}]) == "❌"
    assert dash.ci_state([], [{"state": "pending"}]) == "⏳"


def test_run_state():
    assert dash.run_state(None) == "-"
    assert dash.run_state({"status": "completed", "conclusion": "success"}) == "✅"
    assert dash.run_state({"status": "completed", "conclusion": "failure"}) == "❌"
    assert dash.run_state({"status": "queued"}) == "⏳"


def fake_api(table):
    def api(path, paginate=False):
        for prefix, value in table.items():
            if path.startswith(prefix):
                if isinstance(value, Exception):
                    raise value
                return value
        raise AssertionError(f"unexpected api call {path}")
    return api


def test_fetch_filters_prs_out_of_issues(monkeypatch):
    monkeypatch.setattr(shell, "gh_api", fake_api({
        "repos/o/a/issues": [
            {"number": 1, "title": "issue", "updated_at": "2026-11-01T00:00:00Z", "html_url": "u1"},
            {"number": 2, "title": "pr", "updated_at": "2026-11-01T00:00:00Z", "html_url": "u2", "pull_request": {}},
        ],
        "repos/o/a/pulls": [{"number": 2, "title": "pr", "updated_at": "2026-11-24T00:00:00Z", "html_url": "u2",
                             "draft": True, "head": {"sha": "abc"}}],
        "repos/o/a/commits/abc/check-runs": {"check_runs": [{"status": "completed", "conclusion": "success"}]},
        "repos/o/a/commits/abc/status": {"statuses": []},
        "repos/o/a/actions/runs": {"workflow_runs": [{"status": "completed", "conclusion": "failure"}]},
        "repos/o/a": {"private": True, "archived": False, "default_branch": "main", "pushed_at": "2026-11-20T00:00:00Z"},
    }))
    rep = dash.fetch("o/a")
    assert [i["number"] for i in rep.issues] == [1]
    assert rep.prs[0]["ci"] == "✅" and rep.prs[0]["isDraft"]
    assert rep.main_ci == "❌" and rep.private


def test_fetch_error_is_captured(monkeypatch):
    err = shell.CommandError(["gh"], 1, "gh: Not Found (HTTP 404)")
    monkeypatch.setattr(shell, "gh_api", fake_api({"repos/o/missing": err}))
    rep = dash.fetch("o/missing")
    assert "404" in rep.error


def test_render_table_and_hidden_titles():
    a = dash.RepoReport("o/a", private=True, pushed_at="2026-11-20T00:00:00Z", main_ci="✅",
                        issues=[{"number": 1, "title": "secret | thing", "updatedAt": "2026-11-01T00:00:00Z", "url": "u"}],
                        prs=[{"number": 2, "title": "secret pr", "updatedAt": "2026-11-24T00:00:00Z",
                              "url": "p", "isDraft": False, "ci": "❌"}])
    b = dash.RepoReport("o/b", error="boom")
    c = dash.RepoReport("o/c", pushed_at="2026-11-25T00:00:00Z")
    text = dash.render([a, b, c], now=NOW)
    assert "[o/a](https://github.com/o/a) 🔒 | 1 | 1 | ✅ | 5d" in text
    assert "error: boom" in text
    assert "❌ [#2](p) secret pr" in text
    assert "secret \\| thing" in text
    assert "## o/c" not in text  # nothing open -> no section
    hidden = dash.render([a], now=NOW, hide_private_titles=True)
    assert "secret" not in hidden and "(title hidden)" in hidden


def test_render_truncates_issue_list():
    issues = [{"number": n, "title": f"t{n}", "updatedAt": f"2026-11-{n:02d}T00:00:00Z", "url": "u"} for n in range(1, 9)]
    text = dash.render([dash.RepoReport("o/a", issues=issues)], now=NOW, show_issues=3)
    assert "[#1](u)" in text and "[#4](u)" not in text and "and 5 more" in text


def test_anonymize_private_leaks_nothing():
    priv = dash.RepoReport("secret-org/hidden-proj", private=True, pushed_at="2026-11-20T00:00:00Z", main_ci="✅",
                           issues=[{"number": 1, "title": "t", "updatedAt": "2026-11-01T00:00:00Z", "url": "https://github.com/secret-org/hidden-proj/issues/1"}],
                           prs=[{"number": 2, "title": "p", "updatedAt": "2026-11-24T00:00:00Z", "isDraft": False,
                                 "url": "https://github.com/secret-org/hidden-proj/pull/2", "ci": "✅"}])
    pub = dash.RepoReport("o/pub", private=False, pushed_at="2026-11-25T00:00:00Z",
                          issues=[{"number": 3, "title": "public one", "updatedAt": "2026-11-01T00:00:00Z", "url": "u3"}])
    text = dash.render([priv, pub], now=NOW, anonymize_private=True)
    assert "secret" not in text and "hidden-proj" not in text
    assert "o/pub" in text and "public one" in text
    assert "1 private repos (anonymized)" in text
    assert "across 2 repos" in text


def test_anonymize_keeps_errors_visible():
    text = dash.render([dash.RepoReport("o/broken", error="boom", private=True)], now=NOW, anonymize_private=True)
    assert "error: boom" in text


def test_fetch_can_skip_pr_ci(monkeypatch):
    calls = []

    def api(path, paginate=False):
        calls.append(path)
        if path.startswith("repos/o/a/pulls"):
            return [{"number": 2, "title": "pr", "updated_at": "2026-11-24T00:00:00Z", "html_url": "u",
                     "draft": False, "head": {"sha": "abc"}}]
        if path.startswith("repos/o/a/issues"):
            return []
        if path.startswith("repos/o/a/actions"):
            return {"workflow_runs": []}
        if path == "repos/o/a":
            return {"private": False, "archived": False, "default_branch": "main", "pushed_at": ""}
        raise AssertionError(path)

    monkeypatch.setattr(shell, "gh_api", api)
    rep = dash.fetch("o/a", pr_ci=False)
    assert rep.prs[0]["ci"] == "-"
    assert not any("check-runs" in c or "/status" in c for c in calls)


def test_fetch_caps_pr_ci_lookups(monkeypatch):
    prs = [{"number": n, "title": "p", "updated_at": "2026-11-24T00:00:00Z", "html_url": "u", "draft": False,
            "head": {"sha": f"s{n}"}} for n in range(dash.MAX_PR_CI_LOOKUPS + 5)]
    looked_up = []

    def api(path, paginate=False):
        if path.startswith("repos/o/a/pulls"):
            return prs
        if path.startswith("repos/o/a/issues"):
            return []
        if path.startswith("repos/o/a/actions"):
            return {"workflow_runs": []}
        if "check-runs" in path:
            looked_up.append(path)
            return {"check_runs": [{"status": "completed", "conclusion": "success"}]}
        if "/status" in path:
            return {"statuses": []}
        return {"private": False, "archived": False, "default_branch": "main", "pushed_at": ""}

    monkeypatch.setattr(shell, "gh_api", api)
    dash.fetch("o/a")
    assert len(looked_up) == dash.MAX_PR_CI_LOOKUPS
