"""Cross-repo status dashboard (issues / PRs / CI) rendered as Markdown."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from . import shell

MAX_PR_CI_LOOKUPS = 30  # per repo; avoids burning API quota on huge PR lists


@dataclass
class RepoReport:
    name: str
    private: bool = False
    archived: bool = False
    default_branch: str = ""
    pushed_at: str = ""
    issues: list[dict] = field(default_factory=list)
    prs: list[dict] = field(default_factory=list)
    main_ci: str = "-"
    error: str = ""


def ci_state(check_runs: list[dict] | None, statuses: list[dict] | None = None) -> str:
    """Collapse check runs + legacy commit statuses into one icon: fail > pending > pass > none."""
    bad = {"failure", "timed_out", "cancelled", "error", "startup_failure", "action_required"}
    ok = {"success", "skipped", "neutral"}
    states: set[str] = set()
    for c in check_runs or []:
        states.add((c.get("conclusion") or "pending") if c.get("status") == "completed" else "pending")
    for s in statuses or []:
        states.add((s.get("state") or "pending").lower())
    if not states:
        return "-"
    if states & bad:
        return "❌"
    if states - ok:
        return "⏳"
    return "✅"


def run_state(run: dict | None) -> str:
    if not run:
        return "-"
    if run.get("status") != "completed":
        return "⏳"
    return "✅" if run.get("conclusion") in ("success", "skipped", "neutral") else "❌"


def _pr_ci(name: str, sha: str) -> str:
    try:
        runs = shell.gh_api(f"repos/{name}/commits/{sha}/check-runs?per_page=100")
        status = shell.gh_api(f"repos/{name}/commits/{sha}/status")
    except shell.CommandError:
        return "?"
    return ci_state((runs or {}).get("check_runs"), (status or {}).get("statuses"))


def fetch(name: str, pr_ci: bool = True) -> RepoReport:
    rep = RepoReport(name=name)
    try:
        info = shell.gh_api(f"repos/{name}")
        rep.private = info["private"]
        rep.archived = info["archived"]
        rep.default_branch = info.get("default_branch") or ""
        rep.pushed_at = info.get("pushed_at") or ""
        # The issues endpoint also returns PRs; keep real issues only.
        raw = shell.gh_api(f"repos/{name}/issues?state=open&per_page=100", paginate=True) or []
        rep.issues = [
            {"number": i["number"], "title": i["title"], "updatedAt": i["updated_at"], "url": i["html_url"]}
            for i in raw if "pull_request" not in i
        ]
        pulls = shell.gh_api(f"repos/{name}/pulls?state=open&per_page=100", paginate=True) or []
        for n, p in enumerate(pulls):
            rep.prs.append({
                "number": p["number"], "title": p["title"], "updatedAt": p["updated_at"],
                "isDraft": p.get("draft", False), "url": p["html_url"],
                # "-" = not looked up (disabled, or beyond MAX_PR_CI_LOOKUPS)
                "ci": _pr_ci(name, p["head"]["sha"]) if pr_ci and n < MAX_PR_CI_LOOKUPS else "-",
            })
        if rep.default_branch and not rep.archived:
            runs = shell.gh_api(
                f"repos/{name}/actions/runs?branch={rep.default_branch}&per_page=1"
            )
            items = (runs or {}).get("workflow_runs") or []
            rep.main_ci = run_state(items[0] if items else None)
    except shell.CommandError as e:
        rep.error = (e.stderr.strip().splitlines() or [str(e)])[-1][:200]
    return rep


def _parse(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def age(ts: str, now: datetime) -> str:
    dt = _parse(ts) if ts else None
    if not dt:
        return "-"
    days = (now - dt).days
    return "today" if days <= 0 else f"{days}d"


def _esc(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def render(reports: list[RepoReport], now: datetime | None = None, show_issues: int = 5,
           hide_private_titles: bool = False, anonymize_private: bool = False) -> str:
    now = now or datetime.now(timezone.utc)
    private: list[RepoReport] = []
    if anonymize_private:
        # Private repos are not listed at all (no name, link or title); only an aggregate remains.
        private = [r for r in reports if r.private and not r.error]
        reports = [r for r in reports if not (r.private and not r.error)]
    out = [f"# Repository dashboard", "", f"_Generated {now:%Y-%m-%d %H:%M} UTC_", ""]
    out += ["| Repo | Issues | PRs | CI (default branch) | Last push |", "|---|---:|---:|:-:|---|"]
    for r in sorted(reports, key=lambda r: (-(len(r.prs) + len(r.issues)), r.name)):
        if r.error:
            out.append(f"| {r.name} | - | - | - | error: {_esc(r.error)} |")
            continue
        flags = (" 🔒" if r.private else "") + (" 📦" if r.archived else "")
        out.append(
            f"| [{r.name}](https://github.com/{r.name}){flags} | {len(r.issues)} | {len(r.prs)} "
            f"| {r.main_ci} | {age(r.pushed_at, now)} |"
        )
    if private:
        out.append(
            f"| _{len(private)} private repos (anonymized)_ | {sum(len(r.issues) for r in private)} "
            f"| {sum(len(r.prs) for r in private)} | - | - |"
        )
    everything = reports + private
    total_i = sum(len(r.issues) for r in everything)
    total_p = sum(len(r.prs) for r in everything)
    out += ["", f"**Total:** {total_i} open issues, {total_p} open PRs across {len(everything)} repos.", ""]

    for r in sorted(reports, key=lambda r: r.name):
        if r.error or not (r.prs or r.issues):
            continue
        out.append(f"## {r.name}")
        out.append("")
        hide = hide_private_titles and r.private
        if r.prs:
            out.append("**Pull requests**")
            for p in sorted(r.prs, key=lambda p: p["number"]):
                draft = " (draft)" if p.get("isDraft") else ""
                title = "(title hidden)" if hide else _esc(p["title"])
                out.append(
                    f"- {p.get('ci', '-')} [#{p['number']}]({p['url']}) "
                    f"{title}{draft} · {age(p['updatedAt'], now)}"
                )
            out.append("")
        if r.issues:
            out.append(f"**Issues** (oldest-updated first, top {show_issues})")
            for i in sorted(r.issues, key=lambda i: i["updatedAt"])[:show_issues]:
                title = "(title hidden)" if hide else _esc(i["title"])
                out.append(f"- [#{i['number']}]({i['url']}) {title} · {age(i['updatedAt'], now)}")
            if len(r.issues) > show_issues:
                out.append(f"- … and {len(r.issues) - show_issues} more")
            out.append("")
    return "\n".join(out).rstrip() + "\n"
