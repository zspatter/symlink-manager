"""`python -m symlink_manager <command> [args...]` dispatcher.

Delegates to the same entry points as the installed console scripts so each
subcommand parses its own arguments.
"""
import sys

from .cli import build_main, deploy_main, format_main, maintain_main, status_main

COMMANDS = {
    "build": build_main,
    "deploy": deploy_main,
    "format": format_main,
    "status": status_main,
    "audit": maintain_main,
}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in COMMANDS:
        print(f"usage: python -m symlink_manager {{{'|'.join(COMMANDS)}}} [args...]")
        sys.exit(2)
    COMMANDS[argv[0]](argv[1:])


if __name__ == "__main__":
    main()
