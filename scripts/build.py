import argparse
import sys
from pathlib import Path

# Import the atomic functions from your existing scripts
from format_skyrim_batch import format_repository
from maintain_repo import run_maintenance
from deploy import execute_deployment, load_config, select_variant, ConfigError

def check_configuration(variant_key):
    """Fail-fast configuration check before the pipeline runs."""
    # The script will act on the directory from which it was called
    repo_root = Path.cwd()
    try:
        master_config = load_config(repo_root)
        select_variant(master_config, variant_key)
    except ConfigError as e:
        print(f"\n[!] FATAL: {e}")
        sys.exit(1)

def run_pipeline(variant_key, is_removal=False):
    """Executes the strict Format -> Maintain -> Deploy pipeline."""
    
    check_configuration(variant_key)

    print("\n" + "=" * 50)
    mode_title = "TEARDOWN" if is_removal else "DEPLOYMENT"
    print(f" INITIATING SKYRIM BATCH {mode_title} PIPELINE".center(50))
    print("=" * 50)
    
    if not is_removal:
        # ---------------------------------------------------------
        # STAGE 1: Format & Sanitize
        # ---------------------------------------------------------
        print("\n>>> STAGE 1: FORMATTING REPOSITORY")
        formatting_success = format_repository(active_variant=variant_key)
        if not formatting_success:
            print("\n[!] FATAL: Pipeline halted due to critical formatting errors.")
            sys.exit(1)
        
        # ---------------------------------------------------------
        # STAGE 2: Maintain Architecture (Health Check & Docs)
        # ---------------------------------------------------------
        print("\n>>> STAGE 2: AUDITING REPOSITORY HEALTH")
        try:
            run_maintenance()
        except Exception as e:
            print(f"\n[!] FATAL: Pipeline halted due to maintenance failure: {e}")
            sys.exit(1)
    else:
        print("\n>>> NOTICE: Teardown mode active. Bypassing formatting and maintenance stages.")

    # ---------------------------------------------------------
    # STAGE 3: Deploy to Target
    # ---------------------------------------------------------
    print(f"\n>>> STAGE 3: EXECUTING TARGET ACTIONS -> {variant_key.upper()}")
    execute_deployment(variant_key, is_removal=is_removal)
    
    print("\n" + "=" * 50)
    print(f" {mode_title} PIPELINE COMPLETE".center(50))
    print("=" * 50 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the full Format -> Maintain -> Deploy pipeline.")
    parser.add_argument("variant", help="The name of the variant to deploy (e.g., lost_legacy_2)")
    parser.add_argument("--remove", action="store_true", help="Remove the symlinks from the target directory instead of deploying.")
    
    args = parser.parse_args()
    run_pipeline(args.variant, is_removal=args.remove)