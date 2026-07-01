"""Shared pytest fixtures.

The ``symlink_support`` fixture gates tests that need *real* symlinks. Creating a
symlink requires a privilege that a non-elevated Windows account lacks unless
Developer Mode is on; POSIX and (elevated) CI runners have it. Gated tests skip
locally on such Windows boxes but run on the CI matrix (ubuntu + windows-latest).
"""
import os

import pytest


@pytest.fixture
def symlink_support(tmp_path):
    """Skip the test if the OS/account cannot create symlinks (e.g. no Dev Mode)."""
    src = tmp_path / "_probe_src"
    src.write_text("x")
    link = tmp_path / "_probe_link"
    try:
        os.symlink(src, link)
    except OSError:
        pytest.skip("symlink creation not permitted in this environment")
    link.unlink()
