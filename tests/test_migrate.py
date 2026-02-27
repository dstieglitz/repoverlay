"""Tests for the migrate command."""

import os
from pathlib import Path

import pytest

from repoverlay.output import Output
from repoverlay.overlay import (
    MigrateError,
    _should_encrypt_at_destination,
    get_decoded_dir,
    get_repo_dir,
    migrate_file,
)
from repoverlay.state import read_state, write_state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_output() -> Output:
    return Output(no_color=True, quiet=False)


def _minimal_config() -> dict:
    return {"overlay": {"repo": "/fake/repo"}}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def env(tmp_path):
    """Standard test environment with main repo and overlay repo side-by-side.

    Layout:
        root_dir/
            .repoverlay/
                repo/          <- overlay repo (bare-ish, no .git for simplicity)
                decoded/
            config/
                app.yaml       <- a plain file in the main repo
        state: empty (no symlinks yet)
    """
    root_dir = tmp_path / "main"
    root_dir.mkdir()
    overlay_dir = root_dir / ".repoverlay"
    overlay_dir.mkdir()
    repo_dir = overlay_dir / "repo"
    repo_dir.mkdir()
    decoded_dir = overlay_dir / "decoded"
    decoded_dir.mkdir()

    # Create a file in the main repo
    (root_dir / "config").mkdir()
    plain_file = root_dir / "config" / "app.yaml"
    plain_file.write_text("key: value\n")

    # Write minimal state
    write_state(root_dir, {
        "symlinks": [],
        "created_directories": [],
        "encrypted_files": {},
    })

    return {
        "root_dir": root_dir,
        "repo_dir": repo_dir,
        "decoded_dir": decoded_dir,
        "plain_file": plain_file,
    }


@pytest.fixture()
def overlay_env(tmp_path):
    """Environment with a file already in the overlay repo.

    Layout:
        root_dir/
            .repoverlay/
                repo/
                    old.yaml   <- file to promote back to main
                decoded/
            old.yaml           <- symlink → .repoverlay/repo/old.yaml
    """
    root_dir = tmp_path / "main"
    root_dir.mkdir()
    overlay_dir = root_dir / ".repoverlay"
    overlay_dir.mkdir()
    repo_dir = overlay_dir / "repo"
    repo_dir.mkdir()
    decoded_dir = overlay_dir / "decoded"
    decoded_dir.mkdir()

    # File in overlay repo
    overlay_file = repo_dir / "old.yaml"
    overlay_file.write_text("config: data\n")

    # Symlink in main repo
    symlink_path = root_dir / "old.yaml"
    rel_target = os.path.relpath(overlay_file, symlink_path.parent)
    symlink_path.symlink_to(rel_target)

    write_state(root_dir, {
        "symlinks": ["old.yaml"],
        "created_directories": [],
        "encrypted_files": {},
    })

    return {
        "root_dir": root_dir,
        "repo_dir": repo_dir,
        "decoded_dir": decoded_dir,
        "overlay_file": overlay_file,
        "symlink_path": symlink_path,
    }


# ---------------------------------------------------------------------------
# Test 1: main → overlay (plain, no encryption)
# ---------------------------------------------------------------------------


def test_migrate_main_to_overlay_plain(env, monkeypatch):
    """Plain file moves to overlay, symlink created at original path, state updated."""
    root_dir = env["root_dir"]
    repo_dir = env["repo_dir"]
    plain_file = env["plain_file"]

    config = _minimal_config()
    output = _make_output()

    # Stub out git operations so we don't need a real repo
    monkeypatch.setattr("repoverlay.overlay.git.add", lambda repo, files: None)
    monkeypatch.setattr("repoverlay.overlay.git.get_tracked_files", lambda repo, paths: [])
    monkeypatch.setattr("repoverlay.overlay.git.rm", lambda repo, files, cached=False: None)

    migrate_file(
        root_dir,
        config,
        str(plain_file),
        None,
        purge_history=False,
        encrypt=False,
        dry_run=False,
        output=output,
    )

    # Original file should be gone, replaced by a symlink
    assert plain_file.is_symlink(), "Original path should now be a symlink"
    # Symlink should resolve to the file in overlay repo
    resolved = plain_file.resolve()
    assert resolved == (repo_dir / "config" / "app.yaml").resolve()

    # File should exist in overlay repo
    assert (repo_dir / "config" / "app.yaml").exists()

    # State should record the new symlink
    state = read_state(root_dir)
    assert "config/app.yaml" in state["symlinks"]


# ---------------------------------------------------------------------------
# Test 2: overlay → main
# ---------------------------------------------------------------------------


def test_migrate_overlay_to_main(overlay_env, monkeypatch):
    """File moves from overlay to main, symlink removed, state cleaned up."""
    root_dir = overlay_env["root_dir"]
    overlay_file = overlay_env["overlay_file"]
    symlink_path = overlay_env["symlink_path"]

    config = _minimal_config()
    output = _make_output()

    monkeypatch.setattr("repoverlay.overlay.git.rm", lambda repo, files, cached=False: None)

    migrate_file(
        root_dir,
        config,
        str(overlay_file),
        None,
        purge_history=False,
        encrypt=False,
        dry_run=False,
        output=output,
    )

    # File should now be a real file in the main repo
    dst = root_dir / "old.yaml"
    assert dst.exists() and not dst.is_symlink(), "Destination should be a real file"
    assert dst.read_text() == "config: data\n"

    # The symlink at the same path should now be a real file, not a symlink
    assert not symlink_path.is_symlink(), "Path should no longer be a symlink"

    # State should no longer list the symlink
    state = read_state(root_dir)
    assert "old.yaml" not in state["symlinks"]


# ---------------------------------------------------------------------------
# Test 3: _should_encrypt_at_destination unit test
# ---------------------------------------------------------------------------


def test_encryption_decision():
    """Unit test _should_encrypt_at_destination — no filesystem interaction."""
    config_with_patterns = {
        "overlay": {
            "repo": "/fake",
            "encrypt_patterns": ["secrets/*", "*.enc.yaml"],
        }
    }
    config_no_patterns = {"overlay": {"repo": "/fake"}}

    # Explicit flag overrides everything
    assert _should_encrypt_at_destination("any/path.txt", config_no_patterns, True) is True

    # Pattern match
    assert _should_encrypt_at_destination(
        "secrets/db.yaml", config_with_patterns, False
    ) is True

    # No match
    assert _should_encrypt_at_destination(
        "config/app.yaml", config_with_patterns, False
    ) is False

    # No patterns in config
    assert _should_encrypt_at_destination(
        "secrets/db.yaml", config_no_patterns, False
    ) is False


# ---------------------------------------------------------------------------
# Test 4: dry run makes no filesystem or state changes
# ---------------------------------------------------------------------------


def test_dry_run_no_changes(env, monkeypatch):
    """Dry run prints plan but leaves filesystem and state unchanged."""
    root_dir = env["root_dir"]
    plain_file = env["plain_file"]
    original_content = plain_file.read_text()

    config = _minimal_config()
    output = _make_output()

    # Ensure git operations are not called in dry run
    calls = []
    monkeypatch.setattr(
        "repoverlay.overlay.git.add",
        lambda repo, files: calls.append(("add", files)),
    )
    monkeypatch.setattr(
        "repoverlay.overlay.git.get_tracked_files",
        lambda repo, paths: calls.append(("ls-files", paths)) or [],
    )

    migrate_file(
        root_dir,
        config,
        str(plain_file),
        None,
        purge_history=False,
        encrypt=False,
        dry_run=True,
        output=output,
    )

    # No git calls should have happened
    assert calls == [], f"Unexpected git calls in dry run: {calls}"

    # File should still be a regular file with original content
    assert plain_file.exists() and not plain_file.is_symlink()
    assert plain_file.read_text() == original_content

    # State should be unchanged
    state = read_state(root_dir)
    assert state["symlinks"] == []
