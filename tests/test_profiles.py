"""Unit tests for profile types: source gathering, link resolvers, registry."""
import json
from pathlib import Path

import pytest

from symlink_manager.config import ConfigError
from symlink_manager.formatters import IdentityFormatter, SkyrimBatchFormatter
from symlink_manager.profiles import (
    gather_sources,
    profile_base,
    resolve_skyrim,
    resolve_dotfiles,
    get_profile_type,
)


def _build_skyrim_repo(tmp_path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "c1.txt").write_text("core")
    (tmp_path / "builds").mkdir()
    (tmp_path / "builds" / "b1.txt").write_text("build")
    (tmp_path / "variants" / "nolvus").mkdir(parents=True)
    (tmp_path / "variants" / "nolvus" / "v1.txt").write_text("variant")
    (tmp_path / "variants" / "nolvus" / "v2.txt").write_text("variant")
    (tmp_path / "manifest.json").write_text(
        json.dumps({"v1.txt": ["nolvus"], "v2.txt": ["other"]}), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# gather_sources
# ---------------------------------------------------------------------------

class TestGatherSources:
    def test_gathers_core_builds_and_routed_variants(self, tmp_path):
        _build_skyrim_repo(tmp_path)
        config = {"include_core": True, "include_builds": True, "variant_folder": "variants/nolvus"}
        names = {p.name for p in gather_sources(config, "nolvus", tmp_path)}
        # v2.txt is routed to "other", so it must not appear for nolvus.
        assert names == {"c1.txt", "b1.txt", "v1.txt"}

    def test_respects_include_toggles(self, tmp_path):
        _build_skyrim_repo(tmp_path)
        config = {"include_core": False, "include_builds": False, "variant_folder": "variants/nolvus"}
        names = {p.name for p in gather_sources(config, "nolvus", tmp_path)}
        assert names == {"v1.txt"}

    def test_honors_source_root_silo(self, tmp_path):
        # Same repo, but the skyrim tree lives under skyrim/ instead of the root.
        _build_skyrim_repo(tmp_path / "skyrim")
        config = {
            "source_root": "skyrim", "include_core": True, "include_builds": True,
            "variant_folder": "variants/nolvus",
        }
        sources = gather_sources(config, "nolvus", tmp_path)
        assert {p.name for p in sources} == {"c1.txt", "b1.txt", "v1.txt"}
        # Every gathered path actually resolves under the siloed subdirectory.
        assert all((tmp_path / "skyrim") in p.parents for p in sources)


# ---------------------------------------------------------------------------
# profile_base (source-root resolution)
# ---------------------------------------------------------------------------

class TestProfileBase:
    def test_defaults_to_repo_root(self, tmp_path):
        assert profile_base({}, tmp_path) == tmp_path

    def test_applies_source_root(self, tmp_path):
        assert profile_base({"source_root": "skyrim"}, tmp_path) == tmp_path / "skyrim"


# ---------------------------------------------------------------------------
# resolve_skyrim (broadcast strategy)
# ---------------------------------------------------------------------------

class TestResolveSkyrim:
    def test_builds_broadcast_link_specs(self, tmp_path):
        _build_skyrim_repo(tmp_path)
        target = tmp_path / "target"
        target.mkdir()
        profile = {
            "type": "skyrim_batch", "target_dir": str(target),
            "include_core": True, "include_builds": False, "variant_folder": "variants/nolvus",
        }
        specs = resolve_skyrim(profile, "nolvus", tmp_path)
        targets = {t.name: t for (_s, t) in specs}
        assert set(targets) == {"c1.txt", "v1.txt"}
        assert all(t.parent == target for t in targets.values())

    def test_missing_target_dir_key_raises(self, tmp_path):
        with pytest.raises(ConfigError, match="target_dir"):
            resolve_skyrim({"include_core": True}, "nolvus", tmp_path)

    def test_nonexistent_target_dir_raises(self, tmp_path):
        profile = {"target_dir": str(tmp_path / "missing"), "variant_folder": "variants/x"}
        with pytest.raises(ConfigError, match="Target directory"):
            resolve_skyrim(profile, "nolvus", tmp_path)


# ---------------------------------------------------------------------------
# resolve_dotfiles (explicit mapping strategy)
# ---------------------------------------------------------------------------

class TestResolveDotfiles:
    def test_maps_links_with_user_expansion(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        monkeypatch.setenv("USERPROFILE", str(home))   # Windows expanduser
        monkeypatch.setenv("HOME", str(home))          # POSIX expanduser
        profile = {"links": {"bashrc": "~/.bashrc", "nvim/init.lua": "~/.config/nvim/init.lua"}}

        specs = dict(resolve_dotfiles(profile, "home", tmp_path))

        assert specs[tmp_path / "bashrc"] == home / ".bashrc"
        assert specs[tmp_path / "nvim" / "init.lua"] == home / ".config" / "nvim" / "init.lua"

    def test_missing_links_raises(self, tmp_path):
        with pytest.raises(ConfigError, match="links"):
            resolve_dotfiles({}, "home", tmp_path)


# ---------------------------------------------------------------------------
# get_profile_type (registry)
# ---------------------------------------------------------------------------

class TestGetProfileType:
    def test_defaults_to_skyrim_batch(self):
        pt = get_profile_type({})
        assert pt.formats is True
        assert pt.resolve_links is resolve_skyrim
        assert isinstance(pt.formatter, SkyrimBatchFormatter)

    def test_dotfiles_type(self):
        pt = get_profile_type({"type": "dotfiles"})
        assert pt.formats is False
        assert pt.resolve_links is resolve_dotfiles
        assert isinstance(pt.formatter, IdentityFormatter)

    def test_unknown_type_raises(self):
        with pytest.raises(ConfigError, match="Unknown profile type"):
            get_profile_type({"type": "bogus"})
