import pytest

from ws import config
from ws.config import ConfigError


def test_parse_defaults_and_paths(tmp_path):
    cfg = config.parse(
        {"root": str(tmp_path), "repo": [{"name": "o/a", "tags": ["x"]}, {"name": "o/b", "path": str(tmp_path / "custom")}]}
    )
    assert cfg.repos[0].path == tmp_path / "a"
    assert cfg.repos[1].path == tmp_path / "custom"
    assert cfg.repos[0].short == "a"


@pytest.mark.parametrize("bad", ["noslash", "a/b/c", "/x", "x/", ""])
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
