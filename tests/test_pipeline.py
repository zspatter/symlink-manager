"""Tests for the Format -> Maintain -> Deploy pipeline orchestration.

These drive ``run_pipeline`` directly. The real deploy step is mocked at
``deploy.os.symlink`` so the full success path runs without symlink privileges;
the failure paths monkeypatch the pipeline's stage functions to assert the
fail-fast exit wiring.
"""
import json

import pytest

from symlink_manager import deploy, pipeline
from symlink_manager.pipeline import run_pipeline


def _skyrim_repo(tmp_path):
    """A skyrim_batch repo with one messy core script and an (empty) manifest."""
    core = tmp_path / "core"
    core.mkdir()
    (core / "c1.txt").write_text(
        "; Spells\nplayer.addspell FireBall 1 ; (0000000F) 'Fire Ball'\n", encoding="utf-8")
    (tmp_path / "manifest.json").write_text(json.dumps({}), encoding="utf-8")
    target = tmp_path / "target"
    target.mkdir()
    (tmp_path / "config.json").write_text(json.dumps({
        "sky": {"type": "skyrim_batch", "target_dir": str(target), "include_core": True}
    }), encoding="utf-8")
    return target


class TestPipelineSuccess:
    def test_full_skyrim_pipeline_formats_audits_deploys(self, tmp_path, capsys, monkeypatch):
        _skyrim_repo(tmp_path)
        monkeypatch.setattr(deploy.os, "symlink", lambda s, d, **kw: None)  # no privilege
        original = (tmp_path / "core" / "c1.txt").read_text(encoding="utf-8")

        run_pipeline("sky", repo_root=tmp_path)

        out = capsys.readouterr().out
        assert "STAGE 1: FORMATTING" in out
        assert "STAGE 2: AUDITING" in out
        assert "STAGE 3" in out and "PIPELINE COMPLETE" in out
        assert (tmp_path / "core" / "c1.txt").read_text(encoding="utf-8") != original  # reformatted
        assert (tmp_path / "manifest.md").exists()                                     # audit wrote docs

    def test_dotfiles_pipeline_skips_format_and_audit(self, tmp_path, capsys, monkeypatch):
        (tmp_path / "dotfiles").mkdir()
        (tmp_path / "dotfiles" / "rc").write_text("x")
        out = tmp_path / "out"
        out.mkdir()
        (tmp_path / "config.json").write_text(json.dumps({
            "home": {"type": "dotfiles", "links": {"dotfiles/rc": str(out / "rc")}}
        }), encoding="utf-8")
        monkeypatch.setattr(deploy.os, "symlink", lambda s, d, **kw: None)

        run_pipeline("home", repo_root=tmp_path)

        out_text = capsys.readouterr().out
        assert "does not require formatting" in out_text
        assert "STAGE 1" not in out_text


class TestPipelineFailFast:
    def test_unknown_variant_exits_1(self, tmp_path):
        (tmp_path / "config.json").write_text("{}", encoding="utf-8")
        with pytest.raises(SystemExit) as exc:
            run_pipeline("ghost", repo_root=tmp_path)
        assert exc.value.code == 1

    def test_formatting_failure_halts_pipeline(self, tmp_path, monkeypatch, capsys):
        _skyrim_repo(tmp_path)
        monkeypatch.setattr(pipeline, "format_tree", lambda *a, **k: False)  # critical error
        with pytest.raises(SystemExit) as exc:
            run_pipeline("sky", repo_root=tmp_path)
        assert exc.value.code == 1
        assert "halted due to critical formatting" in capsys.readouterr().out

    def test_maintenance_failure_halts_pipeline(self, tmp_path, monkeypatch, capsys):
        _skyrim_repo(tmp_path)
        monkeypatch.setattr(pipeline, "format_tree", lambda *a, **k: True)  # formatting passes

        def boom(*a, **k):
            raise RuntimeError("audit exploded")

        monkeypatch.setattr(pipeline, "run_maintenance", boom)
        with pytest.raises(SystemExit) as exc:
            run_pipeline("sky", repo_root=tmp_path)
        assert exc.value.code == 1
        assert "maintenance failure" in capsys.readouterr().out

    def test_deploy_error_propagates_exit_code(self, tmp_path):
        # dotfiles skips format/audit; a missing source makes the deploy stage fail.
        out = tmp_path / "out"
        out.mkdir()
        (tmp_path / "config.json").write_text(json.dumps({
            "home": {"type": "dotfiles", "links": {"dotfiles/missing": str(out / "x")}}
        }), encoding="utf-8")
        with pytest.raises(SystemExit) as exc:
            run_pipeline("home", repo_root=tmp_path)
        assert exc.value.code == 1
