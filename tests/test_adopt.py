"""Unit tests for the adopt command (capture machine files into the repo)."""
import json
import os

from symlink_manager import deploy
from symlink_manager.adopt import AdoptStatus, adopt_link, run_adopt

# ---------------------------------------------------------------------------
# adopt_link
# ---------------------------------------------------------------------------

class TestAdoptLink:
    def test_already_in_repo(self, tmp_path):
        source = tmp_path / "s"
        source.write_text("x")
        target = tmp_path / "t"
        target.write_text("y")
        assert adopt_link(source, target) == AdoptStatus.ALREADY_IN_REPO

    def test_nothing_to_adopt(self, tmp_path):
        assert adopt_link(tmp_path / "s", tmp_path / "t") == AdoptStatus.NOTHING_TO_ADOPT

    def test_target_is_symlink(self, tmp_path, symlink_support):
        other = tmp_path / "other"
        other.write_text("x")
        target = tmp_path / "t"
        os.symlink(other, target)
        assert adopt_link(tmp_path / "s", target) == AdoptStatus.TARGET_IS_SYMLINK

    def test_adopts_real_file_into_repo(self, tmp_path, monkeypatch):
        # Mock os.symlink so the link-back step runs without symlink privileges.
        monkeypatch.setattr(deploy.os, "symlink", lambda s, d, **kw: None)
        source = tmp_path / "dotfiles" / "rc"          # not in repo yet
        target = tmp_path / "out" / "rc"
        target.parent.mkdir(parents=True)
        target.write_text("machine config")

        assert adopt_link(source, target) == AdoptStatus.ADOPTED
        assert source.read_text() == "machine config"  # captured into the repo

    def test_dry_run_does_not_move(self, tmp_path):
        source = tmp_path / "dotfiles" / "rc"
        target = tmp_path / "out" / "rc"
        target.parent.mkdir(parents=True)
        target.write_text("machine config")

        assert adopt_link(source, target, dry_run=True) == AdoptStatus.ADOPTED
        assert not source.exists()                      # nothing moved
        assert target.read_text() == "machine config"   # untouched

    def test_relative_links_back_relative(self, tmp_path, monkeypatch):
        captured = []
        monkeypatch.setattr(deploy.os, "symlink", lambda src, dst, **kw: captured.append(str(src)))
        source = tmp_path / "dotfiles" / "rc"          # not in repo yet
        target = tmp_path / "out" / "rc"
        target.parent.mkdir(parents=True)
        target.write_text("machine config")

        assert adopt_link(source, target, relative=True) == AdoptStatus.ADOPTED
        assert captured and not os.path.isabs(captured[0])   # linked back relatively


# ---------------------------------------------------------------------------
# run_adopt
# ---------------------------------------------------------------------------

class TestRunAdopt:
    def test_captures_missing_source(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(deploy.os, "symlink", lambda s, d, **kw: None)
        (tmp_path / "out").mkdir()
        (tmp_path / "out" / "rc").write_text("machine")
        config = {"home": {"type": "dotfiles", "links": {
            "dotfiles/rc": str(tmp_path / "out" / "rc"),
        }}}
        (tmp_path / "config.json").write_text(json.dumps(config), encoding="utf-8")

        run_adopt("home", repo_root=tmp_path)

        report = capsys.readouterr().out
        assert "adopted" in report
        assert (tmp_path / "dotfiles" / "rc").read_text() == "machine"

    def test_unknown_variant_reports_error(self, tmp_path, capsys):
        (tmp_path / "config.json").write_text(json.dumps({"home": {"type": "dotfiles", "links": {}}}), encoding="utf-8")
        run_adopt("ghost", repo_root=tmp_path)
        assert "ERROR" in capsys.readouterr().out

    def test_warns_on_conflicting_targets(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(deploy.os, "symlink", lambda s, d, **kw: None)
        (tmp_path / "out").mkdir()
        (tmp_path / "out" / "shared").write_text("machine")
        shared = str(tmp_path / "out" / "shared")  # two sources capture one target
        config = {"home": {"type": "dotfiles", "links": {
            "dotfiles/a": shared,
            "dotfiles/b": shared,
        }}}
        (tmp_path / "config.json").write_text(json.dumps(config), encoding="utf-8")

        run_adopt("home", repo_root=tmp_path)

        assert "CONFLICT" in capsys.readouterr().out
