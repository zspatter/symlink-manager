"""Formatter implementations and a name->instance registry."""
from .base import Formatter
from .identity import IdentityFormatter
from .skyrim_batch import SkyrimBatchFormatter

# Registry of available formatters, keyed by the name a profile type refers to.
# A plain dict is deliberate: with a handful of in-repo formatters, an
# entry-point plugin system would be over-engineering.
FORMATTERS: dict[str, Formatter] = {
    "identity": IdentityFormatter(),
    "skyrim_batch": SkyrimBatchFormatter(),
}

__all__ = ["Formatter", "IdentityFormatter", "SkyrimBatchFormatter", "FORMATTERS"]
