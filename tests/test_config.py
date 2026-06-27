"""Unit tests for config loading + variant selection."""
import json

import pytest

from symlink_manager.config import ConfigError, load_config, select_variant


def write_config(tmp_path, data):
    (tmp_path / "config.json").write_text(json.dumps(data), encoding="utf-8")


class TestLoadConfig:
    def test_returns_parsed_config(self, tmp_path):
        write_config(tmp_path, {"nolvus": {"target_dir": "D:/x"}})
        assert load_config(tmp_path) == {"nolvus": {"target_dir": "D:/x"}}

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(ConfigError, match="missing"):
            load_config(tmp_path)


class TestSelectVariant:
    def test_returns_variant_block(self):
        config = {"nolvus": {"target_dir": "D:/x"}}
        assert select_variant(config, "nolvus") == {"target_dir": "D:/x"}

    def test_unknown_variant_raises(self):
        with pytest.raises(ConfigError, match="not defined"):
            select_variant({"nolvus": {}}, "ghost")
