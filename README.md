# workspacehack

Manage many GitHub repositories from one place.

- **`ws dash`** – one Markdown page with open issues, PRs and CI status for every repo.
- **`ws clone / pull / status / run`** – clone everything, fast-forward every clean repo, see which repos are dirty or behind, and run a command in all of them.
- **`ws init`** – generate the repo list from your GitHub account.

Python 3.10+ and the [GitHub CLI](https://cli.github.com/) (`gh auth login`). No other dependencies.

## Quick start

```sh
git clone https://github.com/codetea-ping999/workspacehack && cd workspacehack
pip install -e .            # or use ./ws.sh without installing

ws init --owner <your-github-login>   # writes repos.toml (skips forks and archived repos)
ws clone                              # into ~/workspace/<owner>/<repo> (change `root` in repos.toml)
ws status
ws dash -o reports/dashboard.md
```

## Commands

All commands except `init` accept `-c repos.toml`, `-t TAG`, `-r REPO` (repeatable) and `-j JOBS`.

| Command | What it does |
|---|---|
| `ws init [--owner X] [-o repos.toml]` | Build `repos.toml` from your account/org |
| `ws list` | Show the managed repos and their paths |
| `ws clone` | Clone repos that are missing locally |
| `ws pull` | `git pull --ff-only` on each repo; skips dirty trees and branches without an upstream |
| `ws status [--fetch]` | Branch, clean/dirty, ahead/behind for each repo (`--fetch` refreshes remote info first; otherwise numbers reflect the last fetch) |
| `ws run -- <cmd…>` | Run a command in every cloned repo, e.g. `ws run -t app -- pytest -q`. Only the first `--` is consumed, so `ws run -- git checkout -- file` works as written |
| `ws dash [-o FILE]` | Markdown dashboard (issues, PRs with CI icon, default-branch CI, last push). `--no-pr-ci` skips the per-PR CI lookups (2 API calls per PR; only the first 30 PRs per repo are looked up anyway) |

`repos.toml` (see `repos.example.toml`) is plain TOML; add `tags = [...]` to group repos and `path = "..."` to override a location. `-r` accepts `owner/name`, or just `name` when it is unique.

### Safety checks

- Repos live at `<root>/<owner>/<repo>`, so `team-a/tools` and `team-b/tools` never share a directory; two repos resolving to the same path is a config error.
- Names must be valid GitHub `owner/repo` names.
- Before `status`, `pull`, `run` or `clone` touches an existing checkout, its `origin` must be the configured repository. Otherwise the repo is reported as an error and **not** operated on (`ws run` exits 126 for it).
- `ws clone` refuses a non-empty directory that is not a git checkout.
- `ws pull` is `--ff-only` and skips dirty trees.

## Daily dashboard in GitHub Actions

`.github/workflows/dashboard.yml` builds the dashboard every day and shows it as the job summary. To enable it:

1. Make **this repository private** – the workflow refuses to run in a public repo, because a public job summary would expose private issue/PR titles.
2. Add a repository secret `WS_TOKEN`: a personal access token that can read your repositories (classic `repo` scope, or fine-grained read access to Issues, Pull requests, Actions and Metadata).

## Privacy

`repos.toml` and `reports/` are git-ignored because they can contain private repository names and issue titles.

For output you intend to share, use `ws dash --anonymize-private`: private repos are collapsed into one aggregate row (no names, links, titles or per-repo counts; they still count toward the totals). `--hide-private-titles` is the weaker option: it hides only titles and still shows private repo names, links and counts.

## Development

```sh
pip install -e ".[test]" && pytest -q
```

The dashboard talks to the GitHub REST API (`gh api`), not GraphQL.
