"""The domain-agnostic symlink engine: create/remove links, tally, summarize.

``execute_deployment`` resolves a profile's link specs (via its profile type) and
drives them through the idempotent, real-file-protecting symlink primitives.
"""
import os
from pathlib import Path
from enum import Enum, auto

from .config import ConfigError, load_config, select_variant
from .profiles import get_profile_type

# ==============================================================================
# Constants
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
# Link Queue
# ==============================================================================

def process_link_queue(link_specs, is_removal):
    """Executes filesystem ops for a list of (source, target) link specs."""
    stats = {status: 0 for status in DeployStatus}

    for source, target in link_specs:
        if is_removal:
            status = safely_remove_symlink(target)
            stats[status] += 1

            match status:
                case DeployStatus.REMOVED:
                    print(f"  [-] Removed link: {target.name}")
                case DeployStatus.ERROR_REAL_FILE:
                    print(f"  [!] Skipped (Real File Protected): {target.name}")
        else:
            status = safely_create_symlink(source, target)
            stats[status] += 1

            match status:
                case DeployStatus.LINKED:
                    print(f"  [+] Linked: {target.name}")
                case DeployStatus.ERROR_REAL_FILE:
                    print(f"  [!] ERROR: Real file blocking symlink at {target.name}")
                case DeployStatus.ERROR_MISSING_SOURCE:
                    print(f"  [!] ERROR: Source missing on disk: {source}")

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

def execute_deployment(variant_key, is_removal=False, repo_root=None):
    """The master controller for a single deployment run."""
    repo_root = repo_root or Path.cwd()

    try:
        master_config = load_config(repo_root)
        profile = select_variant(master_config, variant_key)
        profile_type = get_profile_type(profile)
        link_specs = profile_type.resolve_links(profile, variant_key, repo_root)
    except ConfigError as e:
        print(f"  [!] ERROR: {e}")
        return

    type_name = profile.get("type", "skyrim_batch")
    print(f"  [*] Profile: {variant_key} ({type_name}) - {len(link_specs)} link(s)\n")

    stats = process_link_queue(link_specs, is_removal)
    print(build_smart_summary(stats, is_removal))
