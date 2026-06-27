"""Unit tests for the symlink engine: link helpers, summary, error translation."""
import os

import pytest

from symlink_manager import deploy
from symlink_manager.deploy import (
    DeployStatus,
    safely_create_symlink,
    safely_remove_symlink,
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
