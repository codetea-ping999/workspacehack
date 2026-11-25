import subprocess

from ws import gitops
from ws.config import Repo


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin:/usr/local/bin"})


def make_pair(tmp_path):
    """A bare 'remote' plus one clone with an initial commit pushed."""
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True, capture_output=True)
    work = tmp_path / "work"
    subprocess.run(["git", "clone", str(remote), str(work)], check=True, capture_output=True)
    (work / "a.txt").write_text("1")
    git(work, "add", ".")
    git(work, "commit", "-m", "init")
    git(work, "push", "-u", "origin", "HEAD:main")
    git(work, "branch", "--set-upstream-to=origin/main", "main")
    return remote, work


def test_parse_status():
    out = "# branch.oid abc\n# branch.head main\n# branch.upstream origin/main\n# branch.ab +2 -3\n1 .M N... 1 1 1 a b f\n? new.txt\n"
    assert gitops.parse_status(out) == ("main", 2, 2, 3, True)


def test_state_clean_dirty_and_uncloned(tmp_path):
    _, work = make_pair(tmp_path)
    repo = Repo("o/work", work)
    s = gitops.state(repo)
    assert s.cloned and s.branch == "main" and s.dirty == 0 and s.has_upstream
    (work / "b.txt").write_text("x")
    assert gitops.state(repo).dirty == 1
    assert not gitops.state(Repo("o/none", tmp_path / "none")).cloned


def test_pull_skips_dirty_and_ffs_clean(tmp_path):
    remote, work = make_pair(tmp_path)
    other = tmp_path / "other"
    subprocess.run(["git", "clone", str(remote), str(other)], check=True, capture_output=True)
    (other / "c.txt").write_text("2")
    git(other, "add", ".")
    git(other, "commit", "-m", "second")
    git(other, "push")

    repo = Repo("o/work", work)
    (work / "dirty.txt").write_text("x")
    assert gitops.pull(repo).startswith("skipped (1 uncommitted")
    (work / "dirty.txt").unlink()
    assert gitops.pull(repo) == "updated"
    assert (work / "c.txt").exists()
    assert gitops.pull(repo) == "up to date"


def test_run_in(tmp_path):
    _, work = make_pair(tmp_path)
    code, out = gitops.run_in(Repo("o/work", work), ["git", "rev-parse", "--abbrev-ref", "HEAD"])
    assert (code, out) == (0, "main")
    assert gitops.run_in(Repo("o/none", tmp_path / "none"), ["true"])[0] == 127
    assert gitops.run_in(Repo("o/work", work), ["definitely-not-a-cmd"])[0] == 127
