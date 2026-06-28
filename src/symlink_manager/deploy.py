"""The domain-agnostic symlink engine: create/remove links, tally, summarize.

``execute_deployment`` resolves a profile's link specs (via its profile type) and
drives them through the idempotent, real-file-protecting symlink primitives.
"""
import os
from pathlib import Path
from enum import Enum, auto

from .config import ConfigError, load_config, select_variant
from .profiles import get_profile_type, current_host_context

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

def safely_create_symlink(source_path, target_path, dry_run=False):
    """Creates a symlink with idempotency checks, protecting real files.

    When ``dry_run`` is set, returns the status that *would* result without
    touching the filesystem.
    """
    if not source_path.exists():
        return DeployStatus.ERROR_MISSING_SOURCE

    if target_path.exists() or target_path.is_symlink():
        if target_path.is_symlink():
            try:
                if target_path.resolve() == source_path.resolve():
                    return DeployStatus.SKIPPED_EXISTING
            except OSError:
                pass
            if dry_run:
                return DeployStatus.LINKED  # would re-point
            target_path.unlink()
        else:
            return DeployStatus.ERROR_REAL_FILE

    if dry_run:
        return DeployStatus.LINKED

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

def safely_remove_symlink(target_path, dry_run=False):
    """Removes a symlink if it exists, aggressively protecting real files."""
    if not target_path.exists() and not target_path.is_symlink():
        return DeployStatus.NOT_FOUND

    if target_path.is_symlink():
        if dry_run:
            return DeployStatus.REMOVED  # would remove
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

def process_link_queue(link_specs, is_removal, dry_run=False):
    """Executes (or, when dry_run, previews) filesystem ops for the link specs."""
    stats = {status: 0 for status in DeployStatus}
    verb = "would " if dry_run else ""

    for source, target in link_specs:
        if is_removal:
            status = safely_remove_symlink(target, dry_run=dry_run)
            stats[status] += 1

            match status:
                case DeployStatus.REMOVED:
                    print(f"  [-] {verb}remove link: {target}")
                case DeployStatus.ERROR_REAL_FILE:
                    print(f"  [!] {verb}skip (real file protected): {target}")
        else:
            status = safely_create_symlink(source, target, dry_run=dry_run)
            stats[status] += 1

            match status:
                case DeployStatus.LINKED:
                    print(f"  [+] {verb}link: {target}")
                case DeployStatus.ERROR_REAL_FILE:
                    print(f"  [!] {verb}error: real file blocking: {target}")
                case DeployStatus.ERROR_MISSING_SOURCE:
                    print(f"  [!] {verb}error: source missing: {source}")

    return stats

def build_smart_summary(stats, is_removal, dry_run=False):
    """Dynamically prints only the deployment statuses that were actually encountered."""
    mode_text = ("DRY RUN " if dry_run else "") + ("TEARDOWN" if is_removal else "DEPLOYMENT")
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

def execute_deployment(variant_key, is_removal=False, repo_root=None,
                       dry_run=False, platform_override=None, host_override=None):
    """The master controller for a single deployment run."""
    repo_root = repo_root or Path.cwd()
    context = current_host_context(platform_override, host_override)

    try:
        master_config = load_config(repo_root)
        profile = select_variant(master_config, variant_key)
        profile_type = get_profile_type(profile)
        link_specs = profile_type.resolve_links(profile, variant_key, repo_root, context)
    except ConfigError as e:
        print(f"  [!] ERROR: {e}")
        return

    if dry_run:
        print("  [*] DRY RUN - no filesystem changes will be made.")
    if (platform_override or host_override) and not dry_run:
        print("  [!] WARNING: --platform/--host override on a real run targets THIS "
              "machine with another host's links; use --dry-run to preview.")

    type_name = profile.get("type", "skyrim_batch")
    print(f"  [*] Profile: {variant_key} ({type_name}) - {len(link_specs)} link(s) "
          f"[{context.platform}/{context.host}]\n")

    stats = process_link_queue(link_specs, is_removal, dry_run=dry_run)
    print(build_smart_summary(stats, is_removal, dry_run=dry_run))
