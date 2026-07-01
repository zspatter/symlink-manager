"""Unit tests for the read-only status / doctor view."""
import json
import os

from symlink_manager.status import LinkState, link_status, run_status

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
        assert run_status("ghost", repo_root=tmp_path) == 1
        assert "ERROR" in capsys.readouterr().out

    def test_conflict_alone_drives_failure_exit(self, tmp_path, capsys):
        # Two sources -> one target. Each link's own state is benign ("not
        # deployed"), but the collision must still make status report failure.
        (tmp_path / "dotfiles").mkdir()
        (tmp_path / "dotfiles" / "a").write_text("x")
        (tmp_path / "dotfiles" / "b").write_text("x")
        out = tmp_path / "out"
        out.mkdir()
        shared = str(out / "shared")
        config = {"home": {"type": "dotfiles", "links": {
            "dotfiles/a": shared,
            "dotfiles/b": shared,
        }}}
        (tmp_path / "config.json").write_text(json.dumps(config), encoding="utf-8")

        assert run_status("home", repo_root=tmp_path) == 1
        assert "CONFLICT" in capsys.readouterr().out


class TestRunStatusJson:
    def _clean_repo(self, tmp_path):
        (tmp_path / "dotfiles").mkdir()
        (tmp_path / "dotfiles" / "rc").write_text("x")
        out = tmp_path / "out"
        out.mkdir()
        config = {"home": {"type": "dotfiles", "links": {"dotfiles/rc": str(out / "rc")}}}
        (tmp_path / "config.json").write_text(json.dumps(config), encoding="utf-8")
        return out

    def test_emits_valid_json_document(self, tmp_path, capsys):
        self._clean_repo(tmp_path)
        code = run_status("home", repo_root=tmp_path, as_json=True)
        assert code == 0
        doc = json.loads(capsys.readouterr().out)  # stdout is pure, parseable JSON
        assert doc["variant"] == "home" and doc["type"] == "dotfiles"
        assert doc["ok"] is True
        assert doc["counts"]["MISSING"] == 1
        assert doc["links"] == [{
            "source": str(tmp_path / "dotfiles" / "rc"),
            "target": str(tmp_path / "out" / "rc"),
            "state": "MISSING",
        }]
        assert doc["conflicts"] == []

    def test_conflict_sets_ok_false_and_exit_1(self, tmp_path, capsys):
        (tmp_path / "dotfiles").mkdir()
        (tmp_path / "dotfiles" / "a").write_text("x")
        (tmp_path / "dotfiles" / "b").write_text("x")
        out = tmp_path / "out"
        out.mkdir()
        shared = str(out / "shared")
        config = {"home": {"type": "dotfiles", "links": {"dotfiles/a": shared, "dotfiles/b": shared}}}
        (tmp_path / "config.json").write_text(json.dumps(config), encoding="utf-8")

        code = run_status("home", repo_root=tmp_path, as_json=True)
        assert code == 1
        doc = json.loads(capsys.readouterr().out)
        assert doc["ok"] is False
        assert len(doc["conflicts"]) == 1 and len(doc["conflicts"][0]["sources"]) == 2

    def test_diagnostics_go_to_stderr_keeping_stdout_pure(self, tmp_path, capsys):
        out = self._clean_repo(tmp_path)
        # Re-write config with an unknown key so a warning is emitted during resolve.
        config = {"home": {"type": "dotfiles",
                           "links": {"dotfiles/rc": str(out / "rc")}, "typo": 1}}
        (tmp_path / "config.json").write_text(json.dumps(config), encoding="utf-8")

        run_status("home", repo_root=tmp_path, as_json=True)

        captured = capsys.readouterr()
        json.loads(captured.out)                              # stdout still parses cleanly
        assert "unrecognized key 'typo'" in captured.err      # warning routed to stderr

    def test_config_error_emits_json_error(self, tmp_path, capsys):
        (tmp_path / "config.json").write_text("{}", encoding="utf-8")
        code = run_status("ghost", repo_root=tmp_path, as_json=True)
        assert code == 1
        doc = json.loads(capsys.readouterr().out)
        assert doc["variant"] == "ghost" and "error" in doc
