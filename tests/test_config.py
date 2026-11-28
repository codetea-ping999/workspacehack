import pytest

from ws import config
from ws.config import ConfigError


def test_parse_defaults_and_paths(tmp_path):
    cfg = config.parse(
        {"root": str(tmp_path), "repo": [{"name": "o/a", "tags": ["x"]}, {"name": "o/b", "path": str(tmp_path / "custom")}]}
    )
    assert cfg.repos[0].path == tmp_path / "o" / "a"
    assert cfg.repos[1].path == tmp_path / "custom"
    assert cfg.repos[0].short == "a"


@pytest.mark.parametrize(
    "bad",
    ["noslash", "a/b/c", "/x", "x/", "", "../x", "o/..", "o/.", "o/r.git", "o/r r", "-o/r", "o/r;rm", "o/$(x)", "o\\r"],
)
def test_bad_names(bad):
    with pytest.raises(ConfigError):
        config.parse({"repo": [{"name": bad}]})


def test_duplicate_rejected():
    with pytest.raises(ConfigError):
        config.parse({"repo": [{"name": "o/a"}, {"name": "O/A"}]})


def test_select_by_tag_and_name(tmp_path):
    cfg = config.parse({"root": str(tmp_path), "repo": [{"name": "o/a", "tags": ["x"]}, {"name": "o/b"}]})
    assert [r.name for r in cfg.select(tag="x")] == ["o/a"]
    assert [r.name for r in cfg.select(only=["b"])] == ["o/b"]
    assert [r.name for r in cfg.select(only=["o/a"])] == ["o/a"]


def test_render_roundtrip(tmp_path):
    text = config.render(str(tmp_path), [("o/a", ["t"]), ("o/b", [])])
    f = tmp_path / "repos.toml"
    f.write_text(text)
    cfg = config.load(f)
    assert [(r.name, r.tags) for r in cfg.repos] == [("o/a", ["t"]), ("o/b", [])]


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="ws init"):
        config.load(tmp_path / "nope.toml")


def test_same_short_name_different_owner_get_distinct_paths(tmp_path):
    cfg = config.parse({"root": str(tmp_path), "repo": [{"name": "team-a/tools"}, {"name": "team-b/tools"}]})
    assert cfg.repos[0].path == tmp_path / "team-a" / "tools"
    assert cfg.repos[1].path == tmp_path / "team-b" / "tools"


def test_explicit_path_collision_rejected(tmp_path):
    with pytest.raises(ConfigError, match="same path"):
        config.parse({"root": str(tmp_path), "repo": [
            {"name": "o/a", "path": str(tmp_path / "x")}, {"name": "o/b", "path": str(tmp_path / "x" / ".." / "x")}]})
    with pytest.raises(ConfigError, match="same path"):
        config.parse({"root": str(tmp_path), "repo": [{"name": "o/a", "path": str(tmp_path / "o" / "b")}, {"name": "o/b"}]})


def test_ambiguous_and_unknown_repo_selection(tmp_path):
    cfg = config.parse({"root": str(tmp_path), "repo": [{"name": "a/tools"}, {"name": "b/tools"}, {"name": "a/x"}]})
    with pytest.raises(ConfigError, match="ambiguous"):
        cfg.select(only=["tools"])
    assert [r.name for r in cfg.select(only=["b/tools", "x"])] == ["b/tools", "a/x"]
    with pytest.raises(ConfigError, match="matches no configured"):
        cfg.select(only=["nope"])


def test_relative_explicit_path_is_relative_to_config(tmp_path):
    cfg = config.parse({"root": "ws", "repo": [{"name": "o/a", "path": "sub/a"}, {"name": "o/b"}]}, base=tmp_path)
    assert cfg.repos[0].path == tmp_path / "sub" / "a"
    assert cfg.repos[1].path == tmp_path / "ws" / "o" / "b"
