"""The Formatter contract shared by every domain formatter."""
from typing import Protocol, runtime_checkable


@runtime_checkable
class Formatter(Protocol):
    """A pure text transform applied to a single source file's contents.

    Implementations must be side-effect free: take the file's text, return the
    normalized text. All file I/O, archiving, and idempotency handling lives in
    the generic ``formatting`` orchestration, not here.
    """

    def format(self, text: str) -> str: ...
