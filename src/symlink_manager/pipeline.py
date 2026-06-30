"""The Format -> Maintain -> Deploy build pipeline.

Stages 1 and 2 (format + audit) run only for profile types that opt into
formatting; types like ``dotfiles`` skip straight to deployment.
"""
import sys
from pathlib import Path

from .config import ConfigError, load_config, select_variant
from .profiles import get_profile_type, profile_base
from .formatting import format_tree
from .maintain import run_maintenance
from .deploy import execute_deployment

def check_configuration(variant_key, repo_root):
    """Fail-fast configuration check before the pipeline runs. Returns the profile."""
    try:
        master_config = load_config(repo_root)
        profile = select_variant(master_config, variant_key)
        get_profile_type(profile)  # validate the declared type is known
    except ConfigError as e:
        print(f"\n[!] FATAL: {e}")
        sys.exit(1)
    return profile

def run_pipeline(variant_key, is_removal=False, repo_root=None):
    """Executes the strict Format -> Maintain -> Deploy pipeline."""
    repo_root = repo_root or Path.cwd()

    profile = check_configuration(variant_key, repo_root)
    profile_type = get_profile_type(profile)

    print("\n" + "=" * 50)
    mode_title = "TEARDOWN" if is_removal else "DEPLOYMENT"
    print(f" INITIATING {mode_title} PIPELINE".center(50))
    print("=" * 50)

    if not is_removal and profile_type.formats:
        base = profile_base(profile, repo_root)

        # ---------------------------------------------------------
        # STAGE 1: Format & Sanitize
        # ---------------------------------------------------------
        print("\n>>> STAGE 1: FORMATTING REPOSITORY")
        formatting_success = format_tree(base, profile_type.formatter, active_variant=variant_key)
        if not formatting_success:
            print("\n[!] FATAL: Pipeline halted due to critical formatting errors.")
            sys.exit(1)

        # ---------------------------------------------------------
        # STAGE 2: Maintain Architecture (Health Check & Docs)
        # ---------------------------------------------------------
        print("\n>>> STAGE 2: AUDITING REPOSITORY HEALTH")
        try:
            run_maintenance(base)
        except Exception as e:
            print(f"\n[!] FATAL: Pipeline halted due to maintenance failure: {e}")
            sys.exit(1)
    elif not is_removal:
        print("\n>>> NOTICE: Profile type does not require formatting. Skipping stages 1-2.")
    else:
        print("\n>>> NOTICE: Teardown mode active. Bypassing formatting and maintenance stages.")

    # ---------------------------------------------------------
    # STAGE 3: Deploy to Target
    # ---------------------------------------------------------
    print(f"\n>>> STAGE 3: EXECUTING TARGET ACTIONS -> {variant_key.upper()}")
    code = execute_deployment(variant_key, is_removal=is_removal, repo_root=repo_root)

    print("\n" + "=" * 50)
    print(f" {mode_title} PIPELINE COMPLETE".center(50))
    print("=" * 50 + "\n")

    if code:
        sys.exit(code)
