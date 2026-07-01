"""Unit tests for the read-only status / doctor view."""
import json
import os

import pytest

from symlink_manager import status
from symlink_manager.status import LinkState, link_status, run_status


@pytest.fixture
def symlink_support(tmp_path):
    src = tmp_path / "_probe_src"
    src.write_text("x")
    link = tmp_path / "_probe_link"
    try:
        os.symlink(src, link)
    except OSError:
        pytest.skip("symlink creation not permitted in this environment")
    link.unlink()


# ---------------------------------------------------------------------------
# link_status
# ---------------------------------------------------------------------------

class TestLinkState:
    def test_missing_source(self, tmp_path):
        assert link_status(tmp_path / "nope.txt", tmp_path / "t.txt") == LinkState.MISSING_SOURCE

    def test_not_deployed(self, tmp_path):
        source = tmp_path / "s.txt"
        source.write_text("x")
        assert link_status(source, tmp_path / "t.txt") == LinkState.MISSING

    def test_blocked_by_real_file(self, tmp_path):
        source = tmp_path / "s.txt"
        source.write_text("x")
        target = tmp_path / "t.txt"
        target.write_text("real")
        assert link_status(source, target) == LinkState.BLOCKED

    def test_linked_ok(self, tmp_path, symlink_support):
        source = tmp_path / "s.txt"
        source.write_text("x")
        target = tmp_path / "t.txt"
        os.symlink(source, target)
        assert link_status(source, target) == LinkState.OK

    def test_wrong_target(self, tmp_path, symlink_support):
        source = tmp_path / "s.txt"
        source.write_text("x")
        other = tmp_path / "other.txt"
        other.write_text("y")
        target = tmp_path / "t.txt"
        os.symlink(other, target)
        assert link_status(source, target) == LinkState.WRONG_TARGET

    def test_broken_symlink(self, tmp_path, symlink_support):
        source = tmp_path / "s.txt"
        source.write_text("x")
        target = tmp_path / "t.txt"
        os.symlink(tmp_path / "ghost", target)  # dangling
        assert link_status(source, target) == LinkState.BROKEN


# ---------------------------------------------------------------------------
# run_status (config -> resolve -> classify)
# ---------------------------------------------------------------------------

class TestRunStatus:
    def test_reports_states_and_filters_by_host(self, tmp_path, capsys):
        (tmp_path / "dotfiles").mkdir()
        (tmp_path / "dotfiles" / "rc").write_text("x")            # source exists -> not deployed
        (tmp_path / "dotfiles" / "blocker").write_text("x")      # source exists -> target blocks it
        out = tmp_path / "out"
        out.mkdir()
        (out / "blocker").write_text("real")                     # real file occupies the target
        config = {"home": {"type": "dotfiles", "links": {
            "dotfiles/rc": {"target": str(out / "rc"), "platforms": ["linux", "macos"]},
            "dotfiles/blocker": {"target": str(out / "blocker"), "platforms": ["linux", "macos"]},
            "dotfiles/win_only": {"target": str(out / "w"), "platforms": "windows"},
        }}}
        (tmp_path / "config.json").write_text(json.dumps(config), encoding="utf-8")

        run_status("home", repo_root=tmp_path, platform_override="linux")

        report = capsys.readouterr().out
        assert "Not deployed" in report
        assert "Blocked (real file)" in report
        assert "STATUS SUMMARY" in report
        assert "win_only" not in report  # windows-only link filtered out on linux

    def test_unknown_variant_reports_error(self, tmp_path, capsys):
        (tmp_path / "config.json").write_text(json.dumps({"home": {"type": "dotfiles", "links": {}}}), encoding="utf-8")
        run_status("ghost", repo_root=tmp_path)
        assert "ERROR" in capsys.readouterr().out
