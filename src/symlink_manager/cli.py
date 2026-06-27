"""Console entry points (argparse). One thin wrapper per command.

Each preserves the original positional/flag arguments and adds a shared
``--repo-root`` (defaulting to the current directory) so the engine no longer
depends on being launched from the parent repo root.
"""
import argparse
import sys
from pathlib import Path

from .config import ConfigError, load_config, select_variant
from .deploy import execute_deployment, SymlinkPermissionError
from .formatting import format_tree
from .maintain import run_maintenance
from .pipeline import run_pipeline
from .profiles import get_profile_type, profile_base


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
    _add_repo_root(parser)
    args = parser.parse_args(argv)

    try:
        execute_deployment(args.variant, is_removal=args.remove, repo_root=_repo_root(args))
    except SymlinkPermissionError as e:
        print(f"\n[FATAL] {e}")
        sys.exit(1)


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


def maintain_main(argv=None):
    parser = argparse.ArgumentParser(
        prog="symlink-audit", description="Audit the repository and regenerate manifest.md.")
    parser.add_argument(
        "--source-root", default=".",
        help="Subdirectory holding manifest.json/core/variants (default: repo root).")
    _add_repo_root(parser)
    args = parser.parse_args(argv)

    run_maintenance(_repo_root(args) / args.source_root)
