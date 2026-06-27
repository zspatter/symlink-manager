"""Unit tests for deploy: config loading, symlink helpers, and source gathering."""
import json
import os

import pytest

import deploy
from deploy import (
    ConfigError,
    DeployStatus,
    load_config,
    select_variant,
    safely_create_symlink,
    safely_remove_symlink,
    gather_sources,
    build_smart_summary,
)


@pytest.fixture
def symlink_support(tmp_path):
    """Skip the test if the OS/account cannot create symlinks (e.g. no Dev Mode)."""
    src = tmp_path / "_probe_src"
    src.write_text("x")
    link = tmp_path / "_probe_link"
    try:
        os.symlink(src, link)
    except OSError:
        pytest.skip("symlink creation not permitted in this environment")
    link.unlink()


def write_config(tmp_path, data):
    (tmp_path / "config.json").write_text(json.dumps(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# Configuration loading
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Symlink helpers
# ---------------------------------------------------------------------------

class TestSafelyCreateSymlink:
    def test_missing_source(self, tmp_path):
        source = tmp_path / "missing.txt"
        target = tmp_path / "link.txt"
        assert safely_create_symlink(source, target) == DeployStatus.ERROR_MISSING_SOURCE

    def test_real_file_at_target_is_protected(self, tmp_path):
        source = tmp_path / "source.txt"
        source.write_text("payload")
        target = tmp_path / "link.txt"
        target.write_text("i am a real file")
        assert safely_create_symlink(source, target) == DeployStatus.ERROR_REAL_FILE
        assert target.read_text() == "i am a real file"  # untouched

    def test_creates_new_link(self, tmp_path, symlink_support):
        source = tmp_path / "source.txt"
        source.write_text("payload")
        target = tmp_path / "link.txt"
        assert safely_create_symlink(source, target) == DeployStatus.LINKED
        assert target.is_symlink()

    def test_existing_matching_link_is_skipped(self, tmp_path, symlink_support):
        source = tmp_path / "source.txt"
        source.write_text("payload")
        target = tmp_path / "link.txt"
        safely_create_symlink(source, target)
        assert safely_create_symlink(source, target) == DeployStatus.SKIPPED_EXISTING


class TestSafelyRemoveSymlink:
    def test_removes_symlink(self, tmp_path, symlink_support):
        source = tmp_path / "source.txt"
        source.write_text("payload")
        target = tmp_path / "link.txt"
        safely_create_symlink(source, target)
        assert safely_remove_symlink(target) == DeployStatus.REMOVED
        assert not target.exists() and not target.is_symlink()

    def test_real_file_is_protected(self, tmp_path):
        target = tmp_path / "real.txt"
        target.write_text("do not delete me")
        assert safely_remove_symlink(target) == DeployStatus.ERROR_REAL_FILE
        assert target.exists()

    def test_missing_target(self, tmp_path):
        assert safely_remove_symlink(tmp_path / "nope.txt") == DeployStatus.NOT_FOUND


# ---------------------------------------------------------------------------
# Source gathering
# ---------------------------------------------------------------------------

class TestGatherSources:
    def _build_repo(self, tmp_path):
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

    def test_gathers_core_builds_and_routed_variants(self, tmp_path):
        self._build_repo(tmp_path)
        config = {
            "include_core": True,
            "include_builds": True,
            "variant_folder": "variants/nolvus",
        }
        names = {p.name for p in gather_sources(config, "nolvus", tmp_path)}
        # v2.txt is routed to "other", so it must not appear for nolvus.
        assert names == {"c1.txt", "b1.txt", "v1.txt"}

    def test_respects_include_toggles(self, tmp_path):
        self._build_repo(tmp_path)
        config = {
            "include_core": False,
            "include_builds": False,
            "variant_folder": "variants/nolvus",
        }
        names = {p.name for p in gather_sources(config, "nolvus", tmp_path)}
        assert names == {"v1.txt"}


# ---------------------------------------------------------------------------
# Summary rendering
# ---------------------------------------------------------------------------

class TestBuildSmartSummary:
    def test_shows_only_nonzero_statuses(self):
        stats = {status: 0 for status in DeployStatus}
        stats[DeployStatus.LINKED] = 3
        summary = build_smart_summary(stats, is_removal=False)
        assert "DEPLOYMENT SUMMARY" in summary
        assert "New Links" in summary and "3" in summary
        assert "Not Found" not in summary  # zero-count status hidden

    def test_teardown_label_and_empty_case(self):
        stats = {status: 0 for status in DeployStatus}
        summary = build_smart_summary(stats, is_removal=True)
        assert "TEARDOWN SUMMARY" in summary
        assert "No actions performed." in summary


# ---------------------------------------------------------------------------
# OS-level error translation (no real symlink privileges required: os.symlink
# is monkeypatched, so these run everywhere including locked-down CI)
# ---------------------------------------------------------------------------

class TestSymlinkErrorTranslation:
    def test_winerror_1314_raises_permission_error(self, tmp_path, monkeypatch):
        source = tmp_path / "source.txt"
        source.write_text("payload")
        target = tmp_path / "link.txt"

        def fake_symlink(src, dst):
            err = OSError("permission denied")
            err.winerror = 1314
            raise err

        monkeypatch.setattr(deploy.os, "symlink", fake_symlink)
        with pytest.raises(deploy.SymlinkPermissionError):
            safely_create_symlink(source, target)

    def test_other_oserror_becomes_error_status(self, tmp_path, monkeypatch):
        source = tmp_path / "source.txt"
        source.write_text("payload")
        target = tmp_path / "link.txt"

        def fake_symlink(src, dst):
            raise OSError("disk gremlins")

        monkeypatch.setattr(deploy.os, "symlink", fake_symlink)
        assert safely_create_symlink(source, target) == DeployStatus.ERROR_OS
