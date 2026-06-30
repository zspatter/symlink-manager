"""Console entry points (argparse). One thin wrapper per command.

Each preserves the original positional/flag arguments and adds a shared
``--repo-root`` (defaulting to the current directory) so the engine no longer
depends on being launched from the parent repo root.
"""
import argparse
import sys
from pathlib import Path

from .adopt import run_adopt
from .config import ConfigError, load_config, select_variant
from .deploy import execute_deployment, SymlinkPermissionError
from .formatting import format_tree
from .maintain import run_maintenance
from .pipeline import run_pipeline
from .profiles import get_profile_type, profile_base
from .status import run_status


def _repo_root(args):
    return Path(args.repo_root).resolve() if args.repo_root else Path.cwd()


def _add_repo_root(parser):
    parser.add_argument(
        "--repo-root", default=None,
        help="Repository root to act on (defaults to the current directory).",
    )


def deploy_main(argv=None):
    parser = argparse.ArgumentParser(
        prog="symlink-deploy", description="Deploy or remove links via symlinks.")
    parser.add_argument("variant", help="The profile/variant to deploy (e.g. lost_legacy_2).")
    parser.add_argument("--remove", action="store_true",
                        help="Remove the symlinks instead of deploying.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview what would change without touching the filesystem.")
    parser.add_argument("--backup", action="store_true",
                        help="Rename a blocking real file aside (<name>.<timestamp>.bak) instead of skipping it.")
    parser.add_argument("--platform", default=None,
                        help="Override the detected platform (windows/macos/linux) for link selection.")
    parser.add_argument("--host", default=None,
                        help="Override the detected hostname for link selection.")
    _add_repo_root(parser)
    args = parser.parse_args(argv)

    try:
        code = execute_deployment(
            args.variant, is_removal=args.remove, repo_root=_repo_root(args),
            dry_run=args.dry_run, platform_override=args.platform, host_override=args.host,
            backup=args.backup,
        )
    except SymlinkPermissionError as e:
        print(f"\n[FATAL] {e}")
        sys.exit(1)
    if code:
        sys.exit(code)


def build_main(argv=None):
    parser = argparse.ArgumentParser(
        prog="symlink-build", description="Run the full Format -> Maintain -> Deploy pipeline.")
    parser.add_argument("variant", help="The profile/variant to deploy (e.g. lost_legacy_2).")
    parser.add_argument("--remove", action="store_true",
                        help="Remove the symlinks instead of deploying.")
    _add_repo_root(parser)
    args = parser.parse_args(argv)

    try:
        run_pipeline(args.variant, is_removal=args.remove, repo_root=_repo_root(args))
    except SymlinkPermissionError as e:
        print(f"\n[!] FATAL: {e}")
        sys.exit(1)


def format_main(argv=None):
    parser = argparse.ArgumentParser(
        prog="symlink-format",
        description="Format the repository's source files in place, without deploying.")
    parser.add_argument("variant", help="The profile whose formatter and active variant to apply.")
    _add_repo_root(parser)
    args = parser.parse_args(argv)
    repo_root = _repo_root(args)

    try:
        master_config = load_config(repo_root)
        profile = select_variant(master_config, args.variant)
        profile_type = get_profile_type(profile)
    except ConfigError as e:
        print(f"\n[!] FATAL: {e}")
        sys.exit(1)

    if not profile_type.formats:
        type_name = profile.get("type", "skyrim_batch")
        print(f"  [*] Profile type '{type_name}' does not require formatting. Nothing to do.")
        return

    base = profile_base(profile, repo_root)
    if not format_tree(base, profile_type.formatter, active_variant=args.variant):
        print("\n[!] FATAL: Formatting halted due to critical errors.")
        sys.exit(1)


def adopt_main(argv=None):
    parser = argparse.ArgumentParser(
        prog="symlink-adopt",
        description="Move existing machine files into the repo and link them back.")
    parser.add_argument("variant", help="The profile/variant to adopt (e.g. dotfiles).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview what would be adopted without touching the filesystem.")
    parser.add_argument("--platform", default=None,
                        help="Override the detected platform (windows/macos/linux) for link selection.")
    parser.add_argument("--host", default=None,
                        help="Override the detected hostname for link selection.")
    _add_repo_root(parser)
    args = parser.parse_args(argv)

    try:
        code = run_adopt(args.variant, repo_root=_repo_root(args), dry_run=args.dry_run,
                         platform_override=args.platform, host_override=args.host)
    except SymlinkPermissionError as e:
        print(f"\n[FATAL] {e}")
        sys.exit(1)
    if code:
        sys.exit(code)


def status_main(argv=None):
    parser = argparse.ArgumentParser(
        prog="symlink-status", description="Report the current state of a profile's links (read-only).")
    parser.add_argument("variant", help="The profile/variant to inspect (e.g. dotfiles).")
    parser.add_argument("--platform", default=None,
                        help="Override the detected platform (windows/macos/linux) for link selection.")
    parser.add_argument("--host", default=None,
                        help="Override the detected hostname for link selection.")
    _add_repo_root(parser)
    args = parser.parse_args(argv)

    code = run_status(args.variant, repo_root=_repo_root(args),
                      platform_override=args.platform, host_override=args.host)
    if code:
        sys.exit(code)


def maintain_main(argv=None):
    parser = argparse.ArgumentParser(
        prog="symlink-audit", description="Audit the repository and regenerate manifest.md.")
    parser.add_argument(
        "--source-root", default=".",
        help="Subdirectory holding manifest.json/core/variants (default: repo root).")
    _add_repo_root(parser)
    args = parser.parse_args(argv)

    run_maintenance(_repo_root(args) / args.source_root)
