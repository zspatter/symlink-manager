"""Unit tests for profile types: source gathering, link resolvers, registry."""
import json
import os
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
    HostContext,
    current_host_context,
    normalize_platform,
)


def ctx(platform="windows", host="PC1"):
    return HostContext(platform, host)


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

    def test_empty_links_is_noop(self, tmp_path):
        assert resolve_dotfiles({"links": {}}, "home", tmp_path, ctx()) == []


# ---------------------------------------------------------------------------
# Conditional links (platform / host filtering)
# ---------------------------------------------------------------------------

class TestConditionalLinks:
    def test_string_value_is_unconditional(self, tmp_path):
        profile = {"links": {"dotfiles/git/.gitconfig": "~/.gitconfig"}}
        assert len(resolve_dotfiles(profile, "home", tmp_path, ctx("linux"))) == 1

    def test_platform_includes_and_excludes(self, tmp_path):
        profile = {"links": {"dotfiles/profile/ps.ps1": {"target": "~/ps", "platforms": "windows"}}}
        assert len(resolve_dotfiles(profile, "h", tmp_path, ctx("windows"))) == 1
        assert resolve_dotfiles(profile, "h", tmp_path, ctx("linux")) == []

    def test_platform_alias_matches_raw_sys_value(self, tmp_path):
        # config says "windows"; a raw "win32" context normalizes to "windows".
        profile = {"links": {"x": {"target": "~/x", "platforms": "windows"}}}
        assert len(resolve_dotfiles(profile, "h", tmp_path, ctx(normalize_platform("win32")))) == 1

    def test_host_filter(self, tmp_path):
        profile = {"links": {"x": {"target": "~/x", "platforms": "macos", "hosts": ["work-mac"]}}}
        assert len(resolve_dotfiles(profile, "h", tmp_path, ctx("macos", "work-mac"))) == 1
        assert resolve_dotfiles(profile, "h", tmp_path, ctx("macos", "home-mac")) == []

    def test_list_candidates_first_match_wins(self, tmp_path, monkeypatch):
        monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        profile = {"links": {"dotfiles/vim/nvim/init.vim": [
            {"target": "~/AppData/Local/nvim/init.vim", "platforms": "windows"},
            {"target": "~/.config/nvim/init.vim", "platforms": ["linux", "macos"]},
        ]}}
        src = tmp_path / "dotfiles" / "vim" / "nvim" / "init.vim"
        win = dict(resolve_dotfiles(profile, "h", tmp_path, ctx("windows")))
        lin = dict(resolve_dotfiles(profile, "h", tmp_path, ctx("linux")))
        assert "AppData" in str(win[src])
        assert ".config" in str(lin[src])

    def test_no_matching_candidate_is_skipped(self, tmp_path):
        profile = {"links": {"x": [{"target": "~/x", "platforms": "macos"}]}}
        assert resolve_dotfiles(profile, "h", tmp_path, ctx("windows")) == []

    def test_missing_target_in_object_raises(self, tmp_path):
        profile = {"links": {"x": {"platforms": "windows"}}}
        with pytest.raises(ConfigError, match="target"):
            resolve_dotfiles(profile, "h", tmp_path, ctx("windows"))

    def test_raw_sys_platform_value_in_config_matches(self, tmp_path):
        # config may use the raw sys.platform spelling ("win32") too.
        profile = {"links": {"x": {"target": "~/x", "platforms": "win32"}}}
        assert len(resolve_dotfiles(profile, "h", tmp_path, ctx("windows"))) == 1

    def test_platform_not_in_multi_list_excluded(self, tmp_path):
        profile = {"links": {"x": {"target": "~/x", "platforms": ["linux", "macos"]}}}
        assert resolve_dotfiles(profile, "h", tmp_path, ctx("windows")) == []

    def test_empty_platforms_list_matches_nothing(self, tmp_path):
        profile = {"links": {"x": {"target": "~/x", "platforms": []}}}
        assert resolve_dotfiles(profile, "h", tmp_path, ctx("windows")) == []

    def test_multiple_hosts_any_matches(self, tmp_path):
        profile = {"links": {"x": {"target": "~/x", "hosts": ["pc-a", "pc-b"]}}}
        assert len(resolve_dotfiles(profile, "h", tmp_path, ctx("windows", "pc-b"))) == 1
        assert resolve_dotfiles(profile, "h", tmp_path, ctx("windows", "pc-c")) == []

    def test_platform_matches_but_host_excludes(self, tmp_path):
        profile = {"links": {"x": {"target": "~/x", "platforms": "windows", "hosts": ["pc-a"]}}}
        assert resolve_dotfiles(profile, "h", tmp_path, ctx("windows", "pc-b")) == []

    def test_host_match_is_case_insensitive(self, tmp_path):
        # platform.node() casing varies by OS; a config host must match regardless.
        profile = {"links": {"x": {"target": "~/x", "hosts": ["Work-Mac"]}}}
        assert len(resolve_dotfiles(profile, "h", tmp_path, ctx("macos", "WORK-MAC"))) == 1
        assert len(resolve_dotfiles(profile, "h", tmp_path, ctx("macos", "work-mac"))) == 1
        assert resolve_dotfiles(profile, "h", tmp_path, ctx("macos", "home-mac")) == []

    def test_list_first_matching_candidate_wins(self, tmp_path, monkeypatch):
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        monkeypatch.setenv("HOME", str(tmp_path))
        # Both candidates apply to windows; the first listed must win.
        profile = {"links": {"x": [
            {"target": "~/first", "platforms": ["windows", "linux"]},
            {"target": "~/second", "platforms": "windows"},
        ]}}
        specs = dict(resolve_dotfiles(profile, "h", tmp_path, ctx("windows")))
        assert specs[tmp_path / "x"] == tmp_path / "first"

    def test_env_var_expansion_in_target(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MYCFG", str(tmp_path / "cfg"))
        profile = {"links": {"x": "$MYCFG/app.conf"}}
        specs = dict(resolve_dotfiles(profile, "h", tmp_path, ctx()))
        assert specs[tmp_path / "x"] == tmp_path / "cfg" / "app.conf"

    def test_empty_string_target_is_skipped_with_warning(self, tmp_path, capsys):
        profile = {"links": {"dotfiles/wt/omp.json": ""}}
        assert resolve_dotfiles(profile, "home", tmp_path, ctx()) == []
        warning = capsys.readouterr().out
        assert "dotfiles/wt/omp.json" in warning and "no target" in warning

    def test_whitespace_target_is_skipped(self, tmp_path):
        profile = {"links": {"x": "   "}}
        assert resolve_dotfiles(profile, "home", tmp_path, ctx()) == []

    def test_empty_target_does_not_drop_valid_siblings(self, tmp_path):
        profile = {"links": {
            "dotfiles/a": "~/a",
            "dotfiles/unfilled": "",
            "dotfiles/b": "~/b",
        }}
        names = {s.name for s, _t in resolve_dotfiles(profile, "home", tmp_path, ctx())}
        assert names == {"a", "b"}


# ---------------------------------------------------------------------------
# Host context
# ---------------------------------------------------------------------------

class TestHostContext:
    def test_normalize_aliases(self):
        assert normalize_platform("win32") == "windows"
        assert normalize_platform("Windows") == "windows"
        assert normalize_platform("darwin") == "macos"
        assert normalize_platform("osx") == "macos"
        assert normalize_platform("linux") == "linux"
        assert normalize_platform("freebsd") == "freebsd"  # unknown passes through

    def test_overrides_win(self):
        c = current_host_context(platform_override="macos", host_override="mb")
        assert c.platform == "macos" and c.host == "mb"

    def test_autodetect_is_sane(self):
        c = current_host_context()
        assert isinstance(c.platform, str) and c.platform
        assert isinstance(c.host, str)


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
