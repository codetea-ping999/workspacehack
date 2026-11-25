"""`ws`: dashboard and bulk operations across many GitHub repositories."""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Sequence

from . import __version__, config, dash, gitops, shell
from .config import ConfigError, Repo


def _pmap(fn: Callable, items: list, jobs: int) -> list:
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as ex:
        return list(ex.map(fn, items))


def _table(rows: list[Sequence[str]], headers: Sequence[str]) -> str:
    widths = [max(len(str(x)) for x in col) for col in zip(headers, *rows)] if rows else [len(h) for h in headers]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    lines = [fmt.format(*headers), fmt.format(*("-" * w for w in widths))]
    lines += [fmt.format(*map(str, r)) for r in rows]
    return "\n".join(lines)


def _selected(args) -> tuple[config.Config, list[Repo]]:
    cfg = config.load(args.config)
    repos = cfg.select(tag=args.tag, only=args.repo)
    if not repos:
        raise ConfigError("no repositories matched (check --tag / --repo and repos.toml)")
    return cfg, repos


def _list_repos(owner: str) -> list[dict]:
    me = shell.gh_api("user").get("login", "")
    if owner.lower() == me.lower():
        return shell.gh_api("user/repos?affiliation=owner&per_page=100", paginate=True)
    try:
        return shell.gh_api(f"orgs/{owner}/repos?per_page=100", paginate=True)
    except shell.CommandError:
        return shell.gh_api(f"users/{owner}/repos?per_page=100", paginate=True)


def cmd_init(args) -> int:
    owner = args.owner or shell.gh_api("user")["login"]
    items = _list_repos(owner)
    keep = [
        i for i in items
        if (args.include_archived or not i["archived"]) and (args.include_forks or not i["fork"])
    ]
    names = sorted(i["full_name"] for i in keep)
    text = config.render(args.root, [(n, []) for n in names])
    if args.output == "-":
        sys.stdout.write(text)
    else:
        from pathlib import Path
        p = Path(args.output)
        if p.exists() and not args.force:
            print(f"{p} already exists (use --force to overwrite)", file=sys.stderr)
            return 1
        p.write_text(text)
        print(f"wrote {p} with {len(names)} repos (skipped {len(items) - len(keep)} archived/fork)")
    return 0


def cmd_list(args) -> int:
    cfg, repos = _selected(args)
    rows = [(r.name, ",".join(r.tags), str(r.path)) for r in repos]
    print(_table(rows, ["repo", "tags", "path"]))
    return 0


def cmd_clone(args) -> int:
    _, repos = _selected(args)

    def one(r: Repo) -> tuple[str, str]:
        try:
            return r.name, gitops.clone(r)
        except shell.CommandError as e:
            return r.name, "error: " + (e.stderr.strip().splitlines() or ["clone failed"])[-1]

    results = _pmap(one, repos, args.jobs)
    print(_table(results, ["repo", "result"]))
    return 1 if any(res.startswith("error") for _, res in results) else 0


def cmd_pull(args) -> int:
    _, repos = _selected(args)
    results = _pmap(lambda r: (r.name, gitops.pull(r)), repos, args.jobs)
    print(_table(results, ["repo", "result"]))
    return 1 if any(res.startswith("error") for _, res in results) else 0


def cmd_status(args) -> int:
    _, repos = _selected(args)
    states = _pmap(gitops.state, repos, args.jobs)
    rows = []
    for s in states:
        if not s.cloned:
            rows.append((s.repo.name, "-", "not cloned", "", ""))
        elif s.error:
            rows.append((s.repo.name, "?", "error", "", s.error))
        else:
            sync = f"↑{s.ahead} ↓{s.behind}" if s.has_upstream else "no upstream"
            rows.append((s.repo.name, s.branch, "dirty" if s.dirty else "clean", sync, f"{s.dirty} changed" if s.dirty else ""))
    print(_table(rows, ["repo", "branch", "tree", "sync", "note"]))
    return 0


def cmd_run(args) -> int:
    _, repos = _selected(args)
    cmd = [c for c in args.command if c != "--"] if args.command[:1] == ["--"] else args.command
    if not cmd:
        print("usage: ws run [--tag T] -- <command ...>", file=sys.stderr)
        return 2
    results = _pmap(lambda r: (r, *gitops.run_in(r, cmd)), repos, args.jobs)
    failed = 0
    for repo, code, out in results:
        mark = "ok" if code == 0 else f"exit {code}"
        print(f"\n=== {repo.name} [{mark}] ===")
        if out:
            print(out)
        failed += code != 0
    print(f"\n{len(results) - failed}/{len(results)} succeeded")
    return 1 if failed else 0


def cmd_dash(args) -> int:
    _, repos = _selected(args)
    reports = _pmap(lambda r: dash.fetch(r.name), repos, args.jobs)
    text = dash.render(reports, show_issues=args.issues, hide_private_titles=args.hide_private_titles)
    if args.output == "-":
        sys.stdout.write(text)
    else:
        with open(args.output, "w") as f:
            f.write(text)
        print(f"wrote {args.output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-c", "--config", default=config.DEFAULT_CONFIG, help="path to repos.toml")
    common.add_argument("-t", "--tag", help="only repos with this tag")
    common.add_argument("-r", "--repo", action="append", help="only this repo (name or owner/name); repeatable")
    common.add_argument("-j", "--jobs", type=int, default=8, help="parallel workers (default 8)")

    p = argparse.ArgumentParser(prog="ws", description=__doc__)
    p.add_argument("--version", action="version", version=f"ws {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="generate repos.toml from your GitHub account")
    s.add_argument("--owner", help="GitHub user/org (default: the logged-in gh user)")
    s.add_argument("--root", default=config.DEFAULT_ROOT, help="local workspace dir")
    s.add_argument("-o", "--output", default=config.DEFAULT_CONFIG, help="output file, or - for stdout")
    s.add_argument("--include-forks", action="store_true")
    s.add_argument("--include-archived", action="store_true")
    s.add_argument("--force", action="store_true", help="overwrite an existing file")
    s.set_defaults(fn=cmd_init)

    for name, fn, help_ in [
        ("list", cmd_list, "list managed repos"),
        ("clone", cmd_clone, "clone missing repos into the workspace"),
        ("pull", cmd_pull, "fast-forward pull every clean repo"),
        ("status", cmd_status, "branch / dirty / ahead-behind for every repo"),
    ]:
        s = sub.add_parser(name, parents=[common], help=help_)
        s.set_defaults(fn=fn)

    s = sub.add_parser("run", parents=[common], help="run a command in every cloned repo")
    s.add_argument("command", nargs=argparse.REMAINDER, help="command after `--`")
    s.set_defaults(fn=cmd_run)

    s = sub.add_parser("dash", parents=[common], help="Markdown dashboard of issues / PRs / CI")
    s.add_argument("-o", "--output", default="-", help="output file (default: stdout)")
    s.add_argument("--issues", type=int, default=5, help="issues listed per repo (default 5)")
    s.add_argument("--hide-private-titles", action="store_true",
                   help="replace issue/PR titles of private repos (safe for public output)")
    s.set_defaults(fn=cmd_dash)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except shell.CommandError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
