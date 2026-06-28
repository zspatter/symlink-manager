"""CLI-layer tests: argparse wiring, flag plumbing, and exit codes.

These drive the entry-point functions with argv lists (the layer the other
tests bypass by calling run_*/execute_* directly).
"""
import json

import pytest

from symlink_manager import deploy
from symlink_manager.cli import (
    deploy_main,
    status_main,
    adopt_main,
    format_main,
    build_main,
    maintain_main,
)


def _dotfiles_repo(tmp_path):
    """A dotfiles repo with a universal, a unix-only, and a windows-only link."""
    src = tmp_path / "dotfiles"
    src.mkdir()
    for name in ("common", "unixrc", "winonly"):
        (src / name).write_text(name)
    out = tmp_path / "out"
    out.mkdir()
    config = {"home": {"type": "dotfiles", "links": {
        "dotfiles/common": str(out / "common"),
        "dotfiles/unixrc": {"target": str(out / "unixrc"), "platforms": ["linux", "macos"]},
        "dotfiles/winonly": {"target": str(out / "winonly"), "platforms": "windows"},
    }}}
    (tmp_path / "config.json").write_text(json.dumps(config), encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# Flag plumbing
# ---------------------------------------------------------------------------

class TestFlagWiring:
    def test_deploy_dry_run(self, tmp_path, capsys):
        _dotfiles_repo(tmp_path)
        deploy_main(["home", "--dry-run", "--repo-root", str(tmp_path)])
        assert "DRY RUN" in capsys.readouterr().out

    def test_deploy_platform_override_filters(self, tmp_path, capsys):
        _dotfiles_repo(tmp_path)
        deploy_main(["home", "--dry-run", "--platform", "linux", "--repo-root", str(tmp_path)])
        out = capsys.readouterr().out
        assert "unixrc" in out          # linux-applicable
        assert "winonly" not in out     # windows-only filtered

    def test_status_runs(self, tmp_path, capsys):
        _dotfiles_repo(tmp_path)
        status_main(["home", "--repo-root", str(tmp_path)])
        assert "STATUS SUMMARY" in capsys.readouterr().out

    def test_adopt_dry_run_runs(self, tmp_path, capsys):
        _dotfiles_repo(tmp_path)
        adopt_main(["home", "--dry-run", "--repo-root", str(tmp_path)])
        assert "ADOPT SUMMARY" in capsys.readouterr().out

    def test_format_on_dotfiles_is_noop(self, tmp_path, capsys):
        _dotfiles_repo(tmp_path)
        format_main(["home", "--repo-root", str(tmp_path)])
        assert "does not require formatting" in capsys.readouterr().out

    def test_build_on_dotfiles_skips_to_deploy(self, tmp_path, capsys, monkeypatch):
        _dotfiles_repo(tmp_path)
        monkeypatch.setattr(deploy.os, "symlink", lambda s, d: None)  # no privilege needed
        build_main(["home", "--repo-root", str(tmp_path)])
        out = capsys.readouterr().out
        assert "does not require formatting" in out
        assert "PIPELINE COMPLETE" in out

    def test_audit_without_manifest_is_noop(self, tmp_path, capsys):
        (tmp_path / "config.json").write_text("{}", encoding="utf-8")
        maintain_main(["--repo-root", str(tmp_path)])
        assert "nothing to audit" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------

class TestExitCodes:
    def test_missing_required_arg_exits_2(self):
        with pytest.raises(SystemExit) as exc:
            deploy_main([])
        assert exc.value.code == 2

    def test_help_exits_0(self):
        with pytest.raises(SystemExit) as exc:
            deploy_main(["--help"])
        assert exc.value.code == 0

    def test_unknown_config_variant_is_handled(self, tmp_path, capsys):
        (tmp_path / "config.json").write_text(json.dumps({"home": {"type": "dotfiles", "links": {}}}), encoding="utf-8")
        deploy_main(["ghost", "--repo-root", str(tmp_path)])   # ConfigError handled internally, no crash
        assert "ERROR" in capsys.readouterr().out

    def test_symlink_permission_error_exits_1(self, tmp_path, monkeypatch):
        _dotfiles_repo(tmp_path)

        def boom(src, dst):
            err = OSError("denied")
            err.winerror = 1314
            raise err

        monkeypatch.setattr(deploy.os, "symlink", boom)
        with pytest.raises(SystemExit) as exc:
            deploy_main(["home", "--repo-root", str(tmp_path)])  # real run hits the mocked symlink
        assert exc.value.code == 1
