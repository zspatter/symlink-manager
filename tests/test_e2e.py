"""End-to-end lifecycle tests over *real* symlinks, driven through the CLI.

Gated on the host being able to create symlinks, so they run on Linux CI (and a
Dev-Mode Windows box) and skip where the privilege is unavailable.
"""
import json
import os

from symlink_manager.cli import deploy_main, status_main, adopt_main


def _write_config(tmp_path, links):
    (tmp_path / "config.json").write_text(
        json.dumps({"home": {"type": "dotfiles", "links": links}}), encoding="utf-8")


class TestDeployLifecycle:
    def test_deploy_status_remove_roundtrip(self, tmp_path, symlink_support, capsys):
        src = tmp_path / "dotfiles"
        src.mkdir()
        (src / "a").write_text("AAA")
        (src / "b").write_text("BBB")
        out = tmp_path / "out"
        out.mkdir()
        link_a = out / "a"
        link_b = out / "sub" / "b"   # nested target exercises parent-dir creation
        _write_config(tmp_path, {
            "dotfiles/a": str(link_a),
            "dotfiles/b": str(link_b),
        })

        # Deploy creates real links (and the missing 'sub/' parent).
        deploy_main(["home", "--repo-root", str(tmp_path)])
        assert link_a.is_symlink() and link_a.read_text() == "AAA"
        assert link_b.is_symlink() and link_b.read_text() == "BBB"

        # Status sees them all linked.
        capsys.readouterr()
        status_main(["home", "--repo-root", str(tmp_path)])
        report = capsys.readouterr().out
        assert "Linked" in report
        assert "Not deployed" not in report and "Blocked" not in report

        # Re-deploy is idempotent (no error, links unchanged).
        deploy_main(["home", "--repo-root", str(tmp_path)])
        assert link_a.is_symlink()

        # Teardown removes the links but leaves the repo sources intact.
        deploy_main(["home", "--remove", "--repo-root", str(tmp_path)])
        assert not link_a.exists() and not link_a.is_symlink()
        assert not link_b.exists()
        assert (src / "a").read_text() == "AAA"

    def test_backup_then_link(self, tmp_path, symlink_support):
        src = tmp_path / "dotfiles"
        src.mkdir()
        (src / "a").write_text("REPO")
        out = tmp_path / "out"
        out.mkdir()
        (out / "a").write_text("MACHINE")   # a real file already occupies the target
        _write_config(tmp_path, {"dotfiles/a": str(out / "a")})

        deploy_main(["home", "--backup", "--repo-root", str(tmp_path)])

        link = out / "a"
        assert link.is_symlink() and link.read_text() == "REPO"
        backups = list(out.glob("a.*.bak"))
        assert len(backups) == 1 and backups[0].read_text() == "MACHINE"

    def test_adopt_captures_and_links(self, tmp_path, symlink_support):
        src = tmp_path / "dotfiles"
        src.mkdir()                          # repo source missing
        out = tmp_path / "out"
        out.mkdir()
        (out / "a").write_text("EXISTING")   # machine file to capture
        _write_config(tmp_path, {"dotfiles/a": str(out / "a")})

        adopt_main(["home", "--repo-root", str(tmp_path)])

        assert (src / "a").read_text() == "EXISTING"   # captured into the repo
        link = out / "a"
        assert link.is_symlink() and link.read_text() == "EXISTING"  # linked back

    def test_deploy_directory_source_links_as_directory(self, tmp_path, symlink_support):
        # End-to-end check of the Windows target_is_directory fix: a directory
        # source must resolve as a real directory link, not a broken file-symlink.
        conf = tmp_path / "dotfiles" / "nvim"
        conf.mkdir(parents=True)
        (conf / "init.lua").write_text("-- config")
        out = tmp_path / "out"
        out.mkdir()
        link = out / "nvim"
        _write_config(tmp_path, {"dotfiles/nvim": str(link)})

        deploy_main(["home", "--repo-root", str(tmp_path)])

        assert link.is_symlink()
        assert link.is_dir()                                    # not a dangling file-symlink
        assert (link / "init.lua").read_text() == "-- config"   # readable through the link

    def test_deploy_repoints_a_wrong_target_symlink(self, tmp_path, symlink_support):
        # A pre-existing symlink pointing at the wrong place must be re-pointed to
        # our source (the unlink + recreate path), not left stale or errored.
        src = tmp_path / "dotfiles"
        src.mkdir()
        (src / "a").write_text("CORRECT")
        stale = tmp_path / "stale"
        stale.write_text("STALE")
        out = tmp_path / "out"
        out.mkdir()
        link = out / "a"
        os.symlink(stale, link)  # already a symlink, but to the wrong target
        _write_config(tmp_path, {"dotfiles/a": str(link)})

        deploy_main(["home", "--repo-root", str(tmp_path)])

        assert link.is_symlink() and link.read_text() == "CORRECT"  # re-pointed to our source
