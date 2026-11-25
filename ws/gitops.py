"""Local git operations across the cloned workspace."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Sequence

from . import shell
from .config import Repo


@dataclass
class RepoState:
    repo: Repo
    cloned: bool
    branch: str = ""
    dirty: int = 0
    ahead: int = 0
    behind: int = 0
    has_upstream: bool = False
    error: str = ""


def parse_status(porcelain_v2: str) -> tuple[str, int, int, int, bool]:
    """Parse `git status --porcelain=v2 --branch` -> (branch, dirty, ahead, behind, has_upstream)."""
    branch, ahead, behind, dirty, upstream = "", 0, 0, 0, False
    for line in porcelain_v2.splitlines():
        if line.startswith("# branch.head "):
            branch = line.split(" ", 2)[2]
        elif line.startswith("# branch.upstream "):
            upstream = True
        elif line.startswith("# branch.ab "):
            _, _, a, b = line.split()
            ahead, behind = int(a.lstrip("+")), abs(int(b))
        elif line and not line.startswith("#"):
            dirty += 1
    return branch, dirty, ahead, behind, upstream


def state(repo: Repo) -> RepoState:
    if not (repo.path / ".git").exists():
        return RepoState(repo, cloned=False)
    try:
        out = shell.run(["git", "status", "--porcelain=v2", "--branch"], cwd=repo.path).stdout
    except shell.CommandError as e:
        return RepoState(repo, cloned=True, error=e.stderr.strip())
    branch, dirty, ahead, behind, upstream = parse_status(out)
    return RepoState(repo, True, branch, dirty, ahead, behind, upstream)


def clone(repo: Repo) -> str:
    if (repo.path / ".git").exists():
        return "already cloned"
    repo.path.parent.mkdir(parents=True, exist_ok=True)
    try:
        shell.run(["gh", "repo", "clone", repo.name, str(repo.path)])
    except (shell.CommandError, FileNotFoundError):
        # gh missing / not logged in: fall back to plain git (works for public repos
        # and for private ones when a git credential helper or SSH key is set up).
        shell.run(["git", "clone", f"https://github.com/{repo.name}.git", str(repo.path)])
    return "cloned"


def pull(repo: Repo) -> str:
    """Fast-forward only, and never touch a dirty tree."""
    st = state(repo)
    if not st.cloned:
        return "skipped (not cloned; run `ws clone`)"
    if st.error:
        return f"error: {st.error}"
    if st.dirty:
        return f"skipped ({st.dirty} uncommitted change(s))"
    if not st.has_upstream:
        return f"skipped (branch {st.branch!r} has no upstream)"
    proc = shell.run(["git", "pull", "--ff-only"], cwd=repo.path, check=False)
    if proc.returncode != 0:
        return "error: " + (proc.stderr.strip().splitlines() or ["pull failed"])[-1]
    last = proc.stdout.strip().splitlines()
    return "up to date" if not last or "up to date" in last[0].lower() else "updated"


def run_in(repo: Repo, cmd: Sequence[str]) -> tuple[int, str]:
    if not (repo.path / ".git").exists():
        return 127, "not cloned"
    try:
        proc = subprocess.run(list(cmd), cwd=repo.path, capture_output=True, text=True)
    except FileNotFoundError:
        return 127, f"command not found: {cmd[0]}"
    return proc.returncode, (proc.stdout + proc.stderr).rstrip()
