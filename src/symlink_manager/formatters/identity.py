"""The no-op formatter used by domains that ship files verbatim (e.g. dotfiles)."""


class IdentityFormatter:
    """Returns the source text untouched."""

    def format(self, text: str) -> str:
        return text
