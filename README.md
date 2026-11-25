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
ws clone                              # into ~/workspace (change `root` in repos.toml)
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
| `ws status` | Branch, clean/dirty, ahead/behind for each repo |
| `ws run -- <cmd…>` | Run a command in every cloned repo, e.g. `ws run -t app -- pytest -q` |
| `ws dash [-o FILE]` | Markdown dashboard (issues, PRs with CI icon, default-branch CI, last push) |

`repos.toml` (see `repos.example.toml`) is plain TOML; add `tags = [...]` to group repos and `path = "..."` to override a location.

## Daily dashboard in GitHub Actions

`.github/workflows/dashboard.yml` builds the dashboard every day and shows it as the job summary. To enable it:

1. Make **this repository private** – the workflow refuses to run in a public repo, because a public job summary would expose private issue/PR titles.
2. Add a repository secret `WS_TOKEN`: a personal access token that can read your repositories (classic `repo` scope, or fine-grained read access to Issues, Pull requests, Actions and Metadata).

## Privacy

`repos.toml` and `reports/` are git-ignored because they can contain private repository names and issue titles. `ws dash --hide-private-titles` replaces titles of private repos if you want to share the output.

## Development

```sh
pip install -e ".[test]" && pytest -q
```

The dashboard talks to the GitHub REST API (`gh api`), not GraphQL.
