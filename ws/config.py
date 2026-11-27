"""Load repos.toml: the list of repositories this workspace manages."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    try:
        import tomli as tomllib  # type: ignore
    except ModuleNotFoundError:
        tomllib = None  # type: ignore

DEFAULT_CONFIG = "repos.toml"
DEFAULT_ROOT = "~/workspace"


class ConfigError(Exception):
    pass


# GitHub: owner = alphanumerics and hyphens; repo = alphanumerics, '-', '_', '.'
_NAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?/[A-Za-z0-9._-]+$")


def valid_name(name: object) -> bool:
    return (
        isinstance(name, str)
        and bool(_NAME_RE.match(name))
        and name.split("/", 1)[1] not in (".", "..")
        and not name.endswith(".git")
    )


@dataclass
class Repo:
    name: str  # "owner/repo"
    path: Path
    tags: list[str] = field(default_factory=list)

    @property
    def short(self) -> str:
        return self.name.split("/", 1)[1]


@dataclass
class Config:
    root: Path
    repos: list[Repo]

    def select(self, tag: str | None = None, only: list[str] | None = None) -> list[Repo]:
        repos = self.repos
        if tag:
            repos = [r for r in repos if tag in r.tags]
        if only:
            picked: list[Repo] = []
            for want in only:
                exact = [r for r in repos if r.name.lower() == want.lower()]
                matches = exact or [r for r in repos if r.short.lower() == want.lower()]
                if not matches:
                    raise ConfigError(f"--repo {want!r} matches no configured repository")
                if len(matches) > 1:
                    names = ", ".join(r.name for r in matches)
                    raise ConfigError(f"--repo {want!r} is ambiguous ({names}); use owner/name")
                if matches[0] not in picked:
                    picked.append(matches[0])
            repos = picked
        return repos


def parse(data: dict, base: Path | None = None) -> Config:
    root = Path(os.path.expanduser(str(data.get("root", DEFAULT_ROOT))))
    if base is not None and not root.is_absolute():
        root = (base / root).resolve()
    repos: list[Repo] = []
    seen: set[str] = set()
    paths: dict[Path, str] = {}
    for i, item in enumerate(data.get("repo", [])):
        name = item.get("name")
        if not valid_name(name):
            raise ConfigError(f"[[repo]] #{i + 1}: 'name' must look like 'owner/repo' (got {name!r})")
        if name.lower() in seen:
            raise ConfigError(f"duplicate repo: {name}")
        seen.add(name.lower())
        # Default location includes the owner, so team-a/tools and team-b/tools never collide.
        if "path" in item:
            path = Path(os.path.expanduser(item["path"]))
            if base is not None and not path.is_absolute():
                path = base / path
        else:
            owner, short = name.split("/", 1)
            path = root / owner / short
        key = Path(os.path.abspath(path))
        if key in paths:
            raise ConfigError(f"{name} and {paths[key]} resolve to the same path: {key}")
        paths[key] = name
        tags = item.get("tags", [])
        if not isinstance(tags, list):
            raise ConfigError(f"{name}: 'tags' must be a list")
        repos.append(Repo(name=name, path=key, tags=[str(t) for t in tags]))
    return Config(root=root, repos=repos)


def load(path: str | os.PathLike = DEFAULT_CONFIG) -> Config:
    p = Path(path)
    if not p.exists():
        raise ConfigError(
            f"{p} not found. Create it with `ws init` (or copy repos.example.toml)."
        )
    if tomllib is None:
        raise ConfigError("Python 3.11+ is required to read TOML (or `pip install tomli`).")
    with p.open("rb") as f:
        return parse(tomllib.load(f), base=p.resolve().parent)


def render(root: str, repos: list[tuple[str, list[str]]]) -> str:
    """Render a repos.toml document."""
    lines = [
        "# repos.toml - repositories managed by workspacehack (`ws`).",
        "# Keep this file out of public repos if it lists private repositories.",
        f'root = "{root}"',
        "",
    ]
    for name, tags in repos:
        lines.append("[[repo]]")
        lines.append(f'name = "{name}"')
        if tags:
            lines.append("tags = [" + ", ".join(f'"{t}"' for t in tags) + "]")
        lines.append("")
    return "\n".join(lines)
