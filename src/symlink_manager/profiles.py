"""Profile types: each bundles a formatter with a source->target link resolver.

A ``config.json`` entry names a ``type`` (defaulting to ``skyrim_batch`` so legacy
configs keep working). The type decides how source files map to link targets and
whether the pipeline runs its formatting stage. Every resolver returns a list of
``LinkSpec`` pairs, which the domain-agnostic link engine in :mod:`deploy`
consumes identically.
"""
import os
import platform
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .config import ConfigError, load_json
from .formatters import FORMATTERS, Formatter

LinkSpec = tuple[Path, Path]  # (source, target)

DEFAULT_PROFILE_TYPE = "skyrim_batch"


# ==============================================================================
# Host context (platform / machine) for conditional dotfile links
# ==============================================================================

_PLATFORM_ALIASES = {
    "win32": "windows", "windows": "windows", "win": "windows",
    "darwin": "macos", "macos": "macos", "mac": "macos", "osx": "macos",
    "linux": "linux", "linux2": "linux",
}

def normalize_platform(name):
    """Canonicalizes a platform string (a sys.platform value or friendly alias)."""
    return _PLATFORM_ALIASES.get(name.lower(), name.lower())

@dataclass(frozen=True)
class HostContext:
    platform: str  # canonical: windows / macos / linux / ...
    host: str      # hostname (platform.node())

def current_host_context(platform_override=None, host_override=None):
    """Builds the host context, honoring optional overrides (for dry-run testing)."""
    plat = platform_override if platform_override else sys.platform
    host = host_override if host_override else platform.node()
    return HostContext(normalize_platform(plat), host)

def _as_list(value):
    return [value] if isinstance(value, str) else list(value)

def _link_matches(candidate, context):
    """Whether a conditional link candidate applies to the current host."""
    platforms = candidate.get("platforms")
    if platforms is not None:
        wanted = {normalize_platform(p) for p in _as_list(platforms)}
        if context.platform not in wanted:
            return False
    hosts = candidate.get("hosts")
    if hosts is not None:
        # Hostnames are case-insensitive (Windows in particular varies the case
        # of platform.node()), so match case-folded on both sides.
        wanted = {h.casefold() for h in _as_list(hosts)}
        if context.host.casefold() not in wanted:
            return False
    return True

def _select_target(value, context, rel_source):
    """Resolves a links value to a target for the current host, or None if filtered out.

    A value may be a bare target string (unconditional), a single conditional
    object ``{"target", "platforms"?, "hosts"?}``, or a list of such candidates
    (first match wins).
    """
    if isinstance(value, str):
        return value
    candidates = value if isinstance(value, list) else [value]
    for candidate in candidates:
        if "target" not in candidate:
            raise ConfigError(f"Link '{rel_source}' has an entry without a 'target'.")
        if _link_matches(candidate, context):
            return candidate["target"]
    return None


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
        manifest_data = load_json(manifest_path, "manifest.json")

        for script_name, active_variants in manifest_data.items():
            if variant_key in active_variants:
                sources.append(variant_dir / script_name)
    else:
        print("  [!] WARNING: manifest.json or variant directory missing. Skipping variant files.")

    return sources


# ==============================================================================
# Link resolvers (source -> target)
# ==============================================================================

def resolve_skyrim(profile, variant_key, repo_root, context=None):
    """Broadcast: every gathered source links flat into one target_dir by name."""
    target = profile.get("target_dir")
    if not target:
        raise ConfigError(f"Profile '{variant_key}' (skyrim_batch) is missing 'target_dir'.")

    target_dir = Path(target)
    if not target_dir.exists():
        raise ConfigError(f"Target directory does not exist: {target_dir}")

    sources = gather_sources(profile, variant_key, repo_root)
    return [(source, target_dir / source.name) for source in sources]

def resolve_dotfiles(profile, variant_key, repo_root, context=None):
    """Explicit mapping: each repo-relative source links to its own target path.

    Link values may be conditional on platform/host; entries that don't apply to
    the current (or overridden) host context are filtered out.
    """
    links = profile.get("links")
    if links is None:
        raise ConfigError(f"Profile '{variant_key}' (dotfiles) has no 'links' mapping.")
    context = context or current_host_context()

    specs = []
    for rel_source, value in links.items():
        target = _select_target(value, context, rel_source)
        if target is None:
            continue  # not applicable to this host
        if not target.strip():
            print(f"  [!] WARNING: link '{rel_source}' has no target; skipping.")
            continue
        source = repo_root / rel_source
        expanded = os.path.expanduser(os.path.expandvars(target))
        specs.append((source, Path(expanded)))
    return specs


# ==============================================================================
# Type registry
# ==============================================================================

@dataclass(frozen=True)
class ProfileType:
    formatter: Formatter
    resolve_links: Callable[..., list]  # (profile, variant_key, repo_root, context) -> [LinkSpec]
    formats: bool  # whether the build pipeline runs the format stage for this type
    known_keys: frozenset  # config keys this type recognizes (for typo detection)

PROFILE_TYPES = {
    "skyrim_batch": ProfileType(
        FORMATTERS["skyrim_batch"], resolve_skyrim, formats=True,
        known_keys=frozenset({
            "type", "source_root", "target_dir",
            "include_core", "include_builds", "variant_folder",
        })),
    "dotfiles": ProfileType(
        FORMATTERS["identity"], resolve_dotfiles, formats=False,
        known_keys=frozenset({"type", "links"})),
}

def get_profile_type(profile):
    """Returns the ProfileType for a profile, defaulting to skyrim_batch."""
    name = profile.get("type", DEFAULT_PROFILE_TYPE)
    if name not in PROFILE_TYPES:
        known = ", ".join(sorted(PROFILE_TYPES))
        raise ConfigError(f"Unknown profile type '{name}'. Known types: {known}.")
    return PROFILE_TYPES[name]

def warn_unknown_keys(profile, profile_type, variant_key):
    """Prints a warning for each profile key the type doesn't recognize (typos).

    Returns the set of unknown keys. Unknown keys are ignored, not fatal, so a
    forward-compatible config still deploys.
    """
    unknown = set(profile) - profile_type.known_keys
    for key in sorted(unknown):
        print(f"  [!] WARNING: profile '{variant_key}' has an unrecognized key "
              f"'{key}' (ignored).")
    return unknown
