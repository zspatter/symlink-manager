"""Unit tests for the symlink engine: link helpers, summary, error translation."""
import json
import os

import pytest

from symlink_manager import deploy
from symlink_manager.deploy import (
    DeployStatus,
    safely_create_symlink,
    safely_remove_symlink,
    process_link_queue,
    execute_deployment,
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

    def test_backup_moves_real_file_then_links(self, tmp_path, monkeypatch):
        # Mock os.symlink so this runs without symlink privileges; we verify the
        # blocking file is renamed aside before the link attempt.
        monkeypatch.setattr(deploy.os, "symlink", lambda s, d: None)
        source = tmp_path / "source.txt"
        source.write_text("new")
        target = tmp_path / "link.txt"
        target.write_text("old")
        assert safely_create_symlink(source, target, backup=True) == DeployStatus.BACKED_UP
        backups = list(tmp_path.glob("link.txt.*.bak"))
        assert len(backups) == 1
        assert backups[0].read_text() == "old"  # original preserved

    def test_backup_dry_run_does_not_move(self, tmp_path):
        source = tmp_path / "source.txt"
        source.write_text("new")
        target = tmp_path / "link.txt"
        target.write_text("old")
        assert safely_create_symlink(source, target, dry_run=True, backup=True) == DeployStatus.BACKED_UP
        assert target.read_text() == "old"          # untouched
        assert not list(tmp_path.glob("*.bak"))     # nothing written

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

    def test_creates_missing_target_parent_dirs(self, tmp_path, monkeypatch):
        # Mock os.symlink so this runs without symlink privileges; we only care
        # that the missing parent chain gets created before the link attempt.
        monkeypatch.setattr(deploy.os, "symlink", lambda s, d: None)
        source = tmp_path / "source.txt"
        source.write_text("payload")
        target = tmp_path / "nested" / "deep" / "link.txt"  # parents don't exist
        assert safely_create_symlink(source, target) == DeployStatus.LINKED
        assert target.parent.exists()

    def test_dry_run_does_not_create_parent_dirs(self, tmp_path):
        source = tmp_path / "source.txt"
        source.write_text("payload")
        target = tmp_path / "nested" / "deep" / "link.txt"
        assert safely_create_symlink(source, target, dry_run=True) == DeployStatus.LINKED
        assert not target.parent.exists()  # preview must not create anything


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

    def test_other_oserror_becomes_error_status(self, tmp_path, monkeypatch, capsys):
        source = tmp_path / "source.txt"
        source.write_text("payload")
        target = tmp_path / "link.txt"

        def fake_symlink(src, dst):
            raise OSError("disk gremlins")

        monkeypatch.setattr(deploy.os, "symlink", fake_symlink)
        assert safely_create_symlink(source, target) == DeployStatus.ERROR_OS
        assert str(target) in capsys.readouterr().out  # failing path is surfaced


# ---------------------------------------------------------------------------
# Dry run (no filesystem mutation)
# ---------------------------------------------------------------------------

class TestDryRun:
    def test_create_dry_run_reports_but_does_not_link(self, tmp_path):
        source = tmp_path / "source.txt"
        source.write_text("payload")
        target = tmp_path / "link.txt"
        assert safely_create_symlink(source, target, dry_run=True) == DeployStatus.LINKED
        assert not target.exists() and not target.is_symlink()  # nothing created

    def test_remove_dry_run_reports_but_keeps_symlink(self, tmp_path, symlink_support):
        source = tmp_path / "source.txt"
        source.write_text("payload")
        target = tmp_path / "link.txt"
        safely_create_symlink(source, target)
        assert safely_remove_symlink(target, dry_run=True) == DeployStatus.REMOVED
        assert target.is_symlink()  # still there

    def test_process_link_queue_dry_run_previews_without_mutation(self, tmp_path):
        fresh_src = tmp_path / "a.txt"; fresh_src.write_text("x")
        fresh_tgt = tmp_path / "a_link.txt"
        real_src = tmp_path / "b.txt"; real_src.write_text("x")
        real_tgt = tmp_path / "b_link.txt"; real_tgt.write_text("real")
        missing_src = tmp_path / "missing.txt"
        missing_tgt = tmp_path / "m_link.txt"
        specs = [(fresh_src, fresh_tgt), (real_src, real_tgt), (missing_src, missing_tgt)]

        stats = process_link_queue(specs, is_removal=False, dry_run=True)

        assert stats[DeployStatus.LINKED] == 1
        assert stats[DeployStatus.ERROR_REAL_FILE] == 1
        assert stats[DeployStatus.ERROR_MISSING_SOURCE] == 1
        assert not fresh_tgt.exists()           # nothing created
        assert real_tgt.read_text() == "real"   # untouched


# ---------------------------------------------------------------------------
# execute_deployment integration (config -> resolve -> queue -> summary)
# ---------------------------------------------------------------------------

class TestExecuteDeploymentIntegration:
    def test_dry_run_filters_by_platform_override(self, tmp_path, capsys):
        (tmp_path / "dotfiles").mkdir()
        (tmp_path / "dotfiles" / "winprofile.ps1").write_text("x")
        (tmp_path / "dotfiles" / "unixrc").write_text("x")
        out = tmp_path / "out"
        out.mkdir()
        config = {"home": {"type": "dotfiles", "links": {
            "dotfiles/winprofile.ps1": {"target": str(out / "winprofile.ps1"), "platforms": "windows"},
            "dotfiles/unixrc": {"target": str(out / "unixrc"), "platforms": ["linux", "macos"]},
        }}}
        (tmp_path / "config.json").write_text(json.dumps(config), encoding="utf-8")

        execute_deployment("home", repo_root=tmp_path, dry_run=True, platform_override="linux")

        out_text = capsys.readouterr().out
        assert "DRY RUN" in out_text
        assert "unixrc" in out_text           # linux-applicable link previewed
        assert "winprofile" not in out_text   # windows-only link filtered out
        assert not (out / "unixrc").exists()   # dry-run wrote nothing

    def test_unknown_variant_reports_error(self, tmp_path, capsys):
        (tmp_path / "config.json").write_text(json.dumps({"home": {"type": "dotfiles", "links": {}}}), encoding="utf-8")
        execute_deployment("ghost", repo_root=tmp_path)
        assert "ERROR" in capsys.readouterr().out
