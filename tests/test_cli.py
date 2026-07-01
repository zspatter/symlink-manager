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


def _skyrim_repo(tmp_path):
    """A minimal skyrim_batch repo with one unformatted core script."""
    core = tmp_path / "core"
    core.mkdir()
    (core / "c1.txt").write_text("setav health 100")  # formatter would rewrite this
    target = tmp_path / "target"
    target.mkdir()
    config = {"sky": {"type": "skyrim_batch", "target_dir": str(target), "include_core": True}}
    (tmp_path / "config.json").write_text(json.dumps(config), encoding="utf-8")
    return target


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
        monkeypatch.setattr(deploy.os, "symlink", lambda s, d, **kw: None)  # no privilege needed
        build_main(["home", "--repo-root", str(tmp_path)])
        out = capsys.readouterr().out
        assert "does not require formatting" in out
        assert "PIPELINE COMPLETE" in out

    def test_build_dry_run_previews_without_writing(self, tmp_path, capsys):
        _dotfiles_repo(tmp_path)
        build_main(["home", "--dry-run", "--repo-root", str(tmp_path)])
        out = capsys.readouterr().out
        assert "DRY RUN" in out
        assert not (tmp_path / "out" / "common").exists()  # nothing created

    def test_build_platform_override_filters(self, tmp_path, capsys):
        _dotfiles_repo(tmp_path)
        build_main(["home", "--dry-run", "--platform", "linux", "--repo-root", str(tmp_path)])
        out = capsys.readouterr().out
        assert "unixrc" in out          # linux-applicable link previewed
        assert "winonly" not in out     # windows-only filtered out

    def test_build_dry_run_skips_mutating_format_stage(self, tmp_path, capsys):
        target = _skyrim_repo(tmp_path)
        original = (tmp_path / "core" / "c1.txt").read_text()
        build_main(["sky", "--dry-run", "--repo-root", str(tmp_path)])
        out = capsys.readouterr().out
        assert "skipping the mutating format/audit stages" in out
        assert (tmp_path / "core" / "c1.txt").read_text() == original  # source not reformatted
        assert not (target / "c1.txt").exists()                        # no link created

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

    def test_unknown_config_variant_exits_1(self, tmp_path, capsys):
        (tmp_path / "config.json").write_text(json.dumps({"home": {"type": "dotfiles", "links": {}}}), encoding="utf-8")
        with pytest.raises(SystemExit) as exc:
            deploy_main(["ghost", "--repo-root", str(tmp_path)])   # ConfigError -> non-zero exit
        assert exc.value.code == 1
        assert "ERROR" in capsys.readouterr().out

    def test_symlink_permission_error_exits_1(self, tmp_path, monkeypatch):
        _dotfiles_repo(tmp_path)

        def boom(src, dst, **kwargs):
            err = OSError("denied")
            err.winerror = 1314
            raise err

        monkeypatch.setattr(deploy.os, "symlink", boom)
        with pytest.raises(SystemExit) as exc:
            deploy_main(["home", "--repo-root", str(tmp_path)])  # real run hits the mocked symlink
        assert exc.value.code == 1

    def test_deploy_blocking_real_file_exits_1(self, tmp_path):
        _dotfiles_repo(tmp_path)
        (tmp_path / "out" / "common").write_text("real")  # blocks a universal link
        with pytest.raises(SystemExit) as exc:
            deploy_main(["home", "--dry-run", "--repo-root", str(tmp_path)])
        assert exc.value.code == 1

    def test_deploy_clean_dry_run_exits_0(self, tmp_path):
        _dotfiles_repo(tmp_path)
        deploy_main(["home", "--dry-run", "--repo-root", str(tmp_path)])  # no raise == exit 0

    def test_status_problem_state_exits_1(self, tmp_path):
        _dotfiles_repo(tmp_path)
        (tmp_path / "out" / "common").write_text("real")  # a real file occupies the target
        with pytest.raises(SystemExit) as exc:
            status_main(["home", "--repo-root", str(tmp_path)])
        assert exc.value.code == 1

    def test_status_not_deployed_exits_0(self, tmp_path):
        _dotfiles_repo(tmp_path)  # sources present, nothing deployed -> not a problem
        status_main(["home", "--repo-root", str(tmp_path)])  # no raise == exit 0

    def test_malformed_config_exits_1(self, tmp_path, capsys):
        (tmp_path / "config.json").write_text("{ not valid json", encoding="utf-8")
        with pytest.raises(SystemExit) as exc:
            deploy_main(["home", "--repo-root", str(tmp_path)])
        assert exc.value.code == 1
        assert "not valid JSON" in capsys.readouterr().out

    def test_audit_malformed_manifest_exits_1(self, tmp_path, capsys):
        (tmp_path / "config.json").write_text("{}", encoding="utf-8")
        (tmp_path / "manifest.json").write_text("{ not valid json", encoding="utf-8")
        with pytest.raises(SystemExit) as exc:
            maintain_main(["--repo-root", str(tmp_path)])
        assert exc.value.code == 1
        assert "not valid JSON" in capsys.readouterr().out

    def test_adopt_error_exits_1(self, tmp_path, monkeypatch):
        # The link-back fails after the capture move -> adopt reports an error.
        def boom(src, dst, **kwargs):
            raise OSError("disk gremlins")

        monkeypatch.setattr(deploy.os, "symlink", boom)
        (tmp_path / "out").mkdir()
        (tmp_path / "out" / "rc").write_text("machine")
        config = {"home": {"type": "dotfiles", "links": {"dotfiles/rc": str(tmp_path / "out" / "rc")}}}
        (tmp_path / "config.json").write_text(json.dumps(config), encoding="utf-8")
        with pytest.raises(SystemExit) as exc:
            adopt_main(["home", "--repo-root", str(tmp_path)])
        assert exc.value.code == 1
