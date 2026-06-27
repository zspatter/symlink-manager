import os
import sys
import argparse
import json
from pathlib import Path
from enum import Enum, auto

# ==============================================================================
# Configuration & Constants
# ==============================================================================

class DeployStatus(Enum):
    LINKED = auto()
    SKIPPED_EXISTING = auto()
    REMOVED = auto()
    NOT_FOUND = auto()
    ERROR_REAL_FILE = auto()
    ERROR_MISSING_SOURCE = auto()
    ERROR_OS = auto()

# Dictionary to map Enums to clean console output labels
STATUS_LABELS = {
    DeployStatus.LINKED: "New Links",
    DeployStatus.SKIPPED_EXISTING: "Existent/Skipped",
    DeployStatus.REMOVED: "Links Removed",
    DeployStatus.NOT_FOUND: "Not Found",
    DeployStatus.ERROR_REAL_FILE: "Protected (Real File)",
    DeployStatus.ERROR_MISSING_SOURCE: "Missing Source",
    DeployStatus.ERROR_OS: "OS Errors"
}

# ==============================================================================
# Configuration Loading
# ==============================================================================

class ConfigError(Exception):
    """Raised when config.json is missing or does not define the variant."""

def load_config(repo_root):
    """Loads and parses the master config.json from the repo root."""
    config_path = repo_root / "config.json"
    if not config_path.exists():
        raise ConfigError(f"Master configuration file missing at {config_path.name}")
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def select_variant(master_config, variant_key):
    """Returns the config block for a single variant, raising if undefined."""
    if variant_key not in master_config:
        raise ConfigError(f"Variant '{variant_key}' is not defined in config.json.")
    return master_config[variant_key]

# ==============================================================================
# Helper Functions (Link Management)
# ==============================================================================

class SymlinkPermissionError(Exception):
    """Raised when the OS denies symlink creation (Windows: needs Dev Mode/admin)."""

def safely_create_symlink(source_path, target_path):
    """Creates a symlink with idempotency checks, protecting real files."""
    if not source_path.exists():
        return DeployStatus.ERROR_MISSING_SOURCE

    if target_path.exists() or target_path.is_symlink():
        if target_path.is_symlink():
            try:
                if target_path.resolve() == source_path.resolve():
                    return DeployStatus.SKIPPED_EXISTING
            except OSError:
                pass
            target_path.unlink() 
        else:
            return DeployStatus.ERROR_REAL_FILE
            
    try:
        os.symlink(source_path, target_path)
        return DeployStatus.LINKED
    except OSError as e:
        if getattr(e, 'winerror', None) == 1314:
            raise SymlinkPermissionError(
                "Windows requires Administrator privileges or 'Developer Mode' "
                "to create symlinks."
            ) from e
        return DeployStatus.ERROR_OS

def safely_remove_symlink(target_path):
    """Removes a symlink if it exists, aggressively protecting real files."""
    if not target_path.exists() and not target_path.is_symlink():
        return DeployStatus.NOT_FOUND
        
    if target_path.is_symlink():
        try:
            target_path.unlink()
            return DeployStatus.REMOVED
        except OSError:
            return DeployStatus.ERROR_OS
    else:
        return DeployStatus.ERROR_REAL_FILE

# ==============================================================================
# Atomic Pipeline Stages
# ==============================================================================

def gather_sources(config, variant_key, repo_root):
    """Builds the list of files to deploy based on configuration and JSON routing."""
    sources = []
    
    # 1. Universal Scripts (Broadcast)
    if config.get("include_core") and (repo_root / "core").exists():
        sources.extend((repo_root / "core").glob("*.txt"))
            
    if config.get("include_builds") and (repo_root / "builds").exists():
        sources.extend((repo_root / "builds").glob("*.txt"))
            
    # 2. Variant Scripts (Routed via JSON)
    manifest_path = repo_root / "manifest.json"
    variant_dir = repo_root / config.get("variant_folder", "")
    
    if manifest_path.exists() and variant_dir.exists():
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest_data = json.load(f)
            
        for script_name, active_variants in manifest_data.items():
            if variant_key in active_variants:
                sources.append(variant_dir / script_name)
    else:
        print("  [!] WARNING: manifest.json or variant directory missing. Skipping variant files.")
        
    return sources

def process_deployment_queue(sources_to_deploy, target_dir, is_removal):
    """Iterates through the queue and executes the file system operations."""
    stats = {status: 0 for status in DeployStatus}
    
    for source_file in sources_to_deploy:
        symlink_target = target_dir / source_file.name
        
        if is_removal:
            status = safely_remove_symlink(symlink_target)
            stats[status] += 1
            
            match status:
                case DeployStatus.REMOVED:
                    print(f"  [-] Removed link: {symlink_target.name}")
                case DeployStatus.ERROR_REAL_FILE:
                    print(f"  [!] Skipped (Real File Protected): {symlink_target.name}")
        else:
            status = safely_create_symlink(source_file, symlink_target)
            stats[status] += 1
            
            match status:
                case DeployStatus.LINKED:
                    print(f"  [+] Linked: {source_file.name}")
                case DeployStatus.ERROR_REAL_FILE:
                    print(f"  [!] ERROR: Real file blocking symlink at {symlink_target.name}")
                case DeployStatus.ERROR_MISSING_SOURCE:
                    print(f"  [!] ERROR: Manifest routed {source_file.name}, but it is missing on disk!")
                    
    return stats

def build_smart_summary(stats, is_removal):
    """Dynamically prints only the deployment statuses that were actually encountered."""
    mode_text = "TEARDOWN" if is_removal else "DEPLOYMENT"
    border = "-" * 50
    
    summary_lines = [
        "",
        border,
        f" {mode_text} SUMMARY".center(50),
        border
    ]
    
    active_stats = {status: count for status, count in stats.items() if count > 0}
    
    if not active_stats:
        summary_lines.append("  No actions performed.")
    else:
        for status, count in active_stats.items():
            label = STATUS_LABELS.get(status, status.name)
            summary_lines.append(f" {label:<21}: {count}")
            
    summary_lines.append(border)
    return "\n".join(summary_lines)

# ==============================================================================
# Execution Orchestration
# ==============================================================================

def execute_deployment(variant_key, is_removal=False):
    """The master controller for a single deployment run."""
    # The script will act on the directory from which it was called
    repo_root = Path.cwd()

    try:
        master_config = load_config(repo_root)
        config = select_variant(master_config, variant_key)
    except ConfigError as e:
        print(f"  [!] ERROR: {e}")
        return

    target_dir = Path(config["target_dir"])
    
    if not target_dir.exists():
        print(f"  [!] ERROR: Target directory does not exist: {target_dir}")
        return
        
    print(f"  [*] Target Path: {target_dir}\n")

    sources = gather_sources(config, variant_key, repo_root)
    stats = process_deployment_queue(sources, target_dir, is_removal)
    print(build_smart_summary(stats, is_removal))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deploy or remove Skyrim batch scripts via symlinks.")
    parser.add_argument("variant", help="The name of the variant to deploy (e.g., lost_legacy_2)")
    parser.add_argument("--remove", action="store_true", help="Remove the symlinks from the target directory instead of deploying.")
    
    args = parser.parse_args()
    try:
        execute_deployment(args.variant, is_removal=args.remove)
    except SymlinkPermissionError as e:
        print(f"\n[FATAL] {e}")
        sys.exit(1)