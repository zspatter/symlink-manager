"""symlink-manager: an idempotent symlink deployment engine.

Reads a centralized config and maps atomic source files from a host repository
to target directories via symlinks. Domain-specific behavior (formatting and
source->target resolution) is pluggable per profile ``type``; the link engine
itself is domain-agnostic.
"""

__version__ = "0.1.0"
