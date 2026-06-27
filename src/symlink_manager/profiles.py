"""Profile types: each bundles a formatter with a source->target link resolver.

A ``config.json`` entry names a ``type`` (defaulting to ``skyrim_batch`` so legacy
configs keep working). The type decides how source files map to link targets and
whether the pipeline runs its formatting stage. Every resolver returns a list of
``LinkSpec`` pairs, which the domain-agnostic link engine in :mod:`deploy`
consumes identically.
"""
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import ConfigError
from .formatters import FORMATTERS, Formatter

LinkSpec = tuple[Path, Path]  # (source, target)

DEFAULT_PROFILE_TYPE = "skyrim_batch"


# ==============================================================================
# Source discovery (Skyrim broadcast layout)
# ==============================================================================

def profile_base(profile, repo_root):
    """Directory a skyrim_batch profile's core/builds/variants/manifest live under.

    Defaults to the repo root; set ``source_root`` (e.g. "skyrim") to silo a
    domain's files under a subdirectory. ``repo_root / "."`` collapses to
    ``repo_root``, so the default is a true no-op.
    """
    return repo_root / profile.get("source_root", ".")

def gather_sources(config, variant_key, repo_root):
    """Builds the list of files to deploy based on configuration and JSON routing."""
    base = profile_base(config, repo_root)
    sources = []

    # 1. Universal Scripts (Broadcast)
    if config.get("include_core") and (base / "core").exists():
        sources.extend((base / "core").glob("*.txt"))

    if config.get("include_builds") and (base / "builds").exists():
        sources.extend((base / "builds").glob("*.txt"))

    # 2. Variant Scripts (Routed via JSON)
    manifest_path = base / "manifest.json"
    variant_dir = base / config.get("variant_folder", "")

    if manifest_path.exists() and variant_dir.exists():
        with open(manifest_path, 'r', encoding='utf-8') as f:
            manifest_data = json.load(f)

        for script_name, active_variants in manifest_data.items():
            if variant_key in active_variants:
                sources.append(variant_dir / script_name)
    else:
        print("  [!] WARNING: manifest.json or variant directory missing. Skipping variant files.")

    return sources


# ==============================================================================
# Link resolvers (source -> target)
# ==============================================================================

def resolve_skyrim(profile, variant_key, repo_root):
    """Broadcast: every gathered source links flat into one target_dir by name."""
    target = profile.get("target_dir")
    if not target:
        raise ConfigError(f"Profile '{variant_key}' (skyrim_batch) is missing 'target_dir'.")

    target_dir = Path(target)
    if not target_dir.exists():
        raise ConfigError(f"Target directory does not exist: {target_dir}")

    sources = gather_sources(profile, variant_key, repo_root)
    return [(source, target_dir / source.name) for source in sources]

def resolve_dotfiles(profile, variant_key, repo_root):
    """Explicit mapping: each repo-relative source links to its own target path."""
    links = profile.get("links")
    if not links:
        raise ConfigError(f"Profile '{variant_key}' (dotfiles) has no 'links' mapping.")

    specs = []
    for rel_source, raw_target in links.items():
        source = repo_root / rel_source
        expanded = os.path.expanduser(os.path.expandvars(raw_target))
        specs.append((source, Path(expanded)))
    return specs


# ==============================================================================
# Type registry
# ==============================================================================

@dataclass(frozen=True)
class ProfileType:
    formatter: Formatter
    resolve_links: Callable[[dict, str, Path], list]
    formats: bool  # whether the build pipeline runs the format stage for this type

PROFILE_TYPES = {
    "skyrim_batch": ProfileType(FORMATTERS["skyrim_batch"], resolve_skyrim, formats=True),
    "dotfiles": ProfileType(FORMATTERS["identity"], resolve_dotfiles, formats=False),
}

def get_profile_type(profile):
    """Returns the ProfileType for a profile, defaulting to skyrim_batch."""
    name = profile.get("type", DEFAULT_PROFILE_TYPE)
    if name not in PROFILE_TYPES:
        known = ", ".join(sorted(PROFILE_TYPES))
        raise ConfigError(f"Unknown profile type '{name}'. Known types: {known}.")
    return PROFILE_TYPES[name]
