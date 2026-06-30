"""Adopt existing machine files into the repo, then link them back.

For each configured link whose repo source doesn't exist yet but whose target is
a real file on this machine, ``adopt`` moves the file into the repo (at the
source path) and replaces the original with a symlink. It's the inverse of
deploy: capture config you already have into version control.
"""
import shutil
from enum import Enum, auto
from pathlib import Path

from .config import ConfigError, load_config, select_variant
from .profiles import get_profile_type, current_host_context
from .deploy import safely_create_symlink, DeployStatus


class AdoptStatus(Enum):
    ADOPTED = auto()           # moved target -> repo source, then linked back
    ALREADY_IN_REPO = auto()   # source already exists; nothing to capture
    NOTHING_TO_ADOPT = auto()  # source missing and target absent
    TARGET_IS_SYMLINK = auto()  # target already a symlink (leave it alone)
    ERROR = auto()


ADOPT_LABELS = {
    AdoptStatus.ADOPTED: "Adopted",
    AdoptStatus.ALREADY_IN_REPO: "Already in repo",
    AdoptStatus.NOTHING_TO_ADOPT: "Nothing to adopt",
    AdoptStatus.TARGET_IS_SYMLINK: "Already a symlink",
    AdoptStatus.ERROR: "Errors",
}


def adopt_link(source_path, target_path, dry_run=False):
    """Captures an existing real file at the target into the repo source + links back."""
    if source_path.exists():
        return AdoptStatus.ALREADY_IN_REPO
    if target_path.is_symlink():
        return AdoptStatus.TARGET_IS_SYMLINK
    if not target_path.exists():
        return AdoptStatus.NOTHING_TO_ADOPT

    # A real file lives at the target and the repo doesn't have it yet.
    if dry_run:
        return AdoptStatus.ADOPTED  # would adopt

    source_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(target_path), str(source_path))  # capture into the repo
    status = safely_create_symlink(source_path, target_path)  # may raise SymlinkPermissionError
    if status in (DeployStatus.LINKED, DeployStatus.SKIPPED_EXISTING):
        return AdoptStatus.ADOPTED
    return AdoptStatus.ERROR


def _summary(stats):
    border = "-" * 50
    lines = ["", border, " ADOPT SUMMARY".center(50), border]
    active = {state: count for state, count in stats.items() if count > 0}
    if not active:
        lines.append("  No links resolved for this host.")
    else:
        for state, count in active.items():
            lines.append(f" {ADOPT_LABELS[state]:<21}: {count}")
    lines.append(border)
    return "\n".join(lines)


def run_adopt(variant_key, repo_root=None, dry_run=False, platform_override=None, host_override=None):
    """Adopts every adoptable link in a profile (moves machine files into the repo).

    Returns a process-style exit code: 0 on success, 1 if configuration failed or
    any link could not be adopted.
    """
    repo_root = repo_root or Path.cwd()
    context = current_host_context(platform_override, host_override)

    try:
        master_config = load_config(repo_root)
        profile = select_variant(master_config, variant_key)
        profile_type = get_profile_type(profile)
        link_specs = profile_type.resolve_links(profile, variant_key, repo_root, context)
    except ConfigError as e:
        print(f"  [!] ERROR: {e}")
        return 1

    if dry_run:
        print("  [*] DRY RUN - no filesystem changes will be made.")
    type_name = profile.get("type", "skyrim_batch")
    print(f"  [*] Adopt: {variant_key} ({type_name}) - {len(link_specs)} link(s) "
          f"[{context.platform}/{context.host}]\n")

    stats = {state: 0 for state in AdoptStatus}
    verb = "would adopt" if dry_run else "adopted"
    for source, target in link_specs:
        state = adopt_link(source, target, dry_run=dry_run)
        stats[state] += 1
        if state is AdoptStatus.ADOPTED:
            print(f"  [+] {verb}: {target} -> {source}")
        elif state is AdoptStatus.ERROR:
            print(f"  [!] error adopting: {target}")

    print(_summary(stats))
    return 1 if stats[AdoptStatus.ERROR] else 0
