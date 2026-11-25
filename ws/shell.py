"""Thin subprocess helpers (kept separate so tests can stub them)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Sequence


class CommandError(Exception):
    def __init__(self, cmd: Sequence[str], code: int, stderr: str):
        super().__init__(f"{' '.join(cmd)} -> exit {code}: {stderr.strip()}")
        self.code = code
        self.stderr = stderr


def run(cmd: Sequence[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise CommandError(cmd, proc.returncode, proc.stderr)
    return proc


def gh_json(args: Sequence[str]) -> Any:
    out = run(["gh", *args]).stdout
    return json.loads(out) if out.strip() else None


def gh_api(path: str, paginate: bool = False) -> Any:
    """Call the GitHub REST API via `gh api`. Paginated results are flattened into one list.

    REST is used on purpose (no GraphQL), so this also works in restricted environments.
    """
    cmd = ["api", path]
    if paginate:
        cmd += ["--paginate", "--slurp"]
    data = gh_json(cmd)
    if paginate and isinstance(data, list):
        flat: list = []
        for page in data:
            flat.extend(page if isinstance(page, list) else [page])
        return flat
    return data
