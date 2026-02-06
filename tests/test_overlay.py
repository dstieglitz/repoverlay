"""Tests for overlay module."""

import os
import subprocess

import pytest
import yaml

from repoverlay.output import Output
from repoverlay.overlay import (
    OverlayError,
    UncommittedChangesError,
    UnpushedCommitsError,
    clone_overlay,
    get_overlay_dir,
    get_repo_dir,
    sync_overlay,
    unlink_overlay,
)
from repoverlay.state import read_state


class TestOverlayPaths:
    """Tests for path helper functions."""

    def test_get_overlay_dir(self, tmp_path):
        """Overlay dir is correct."""
        result = get_overlay_dir(tmp_path)
        assert result == tmp_path / ".repoverlay"

    def test_get_repo_dir(self, tmp_path):
        """Repo dir is correct."""
        result = get_repo_dir(tmp_path)
        assert result == tmp_path / ".repoverlay" / "repo"


class TestCloneOverlay:
    """Tests for clone_overlay function."""

    def test_clone_creates_repo_dir(self, tmp_main_repo, sample_config):
        """Clone creates .repoverlay/repo/ directory."""
        clone_overlay(tmp_main_repo, sample_config)

        repo_dir = get_repo_dir(tmp_main_repo)
        assert repo_dir.is_dir()
        assert (repo_dir / ".git").is_dir()

    def test_clone_without_mappings(self, tmp_main_repo, tmp_overlay_repo):
        """Clone without mappings creates symlinks for all files."""
        config = {
            "version": 1,
            "overlay": {
                "repo": str(tmp_overlay_repo),
            },
        }
        clone_overlay(tmp_main_repo, config)

        # All files from overlay should be symlinked at their original paths
        assert (tmp_main_repo / ".env.production").is_symlink()
        assert (tmp_main_repo / ".env.production").read_text() == "API_KEY=xxx"
        assert (tmp_main_repo / "secrets" / "db.yaml").is_symlink()
        assert (tmp_main_repo / "secrets" / "db.yaml").read_text() == "password: secret"

    def test_clone_local_directory(self, tmp_main_repo, tmp_path):
        """Clone from local directory copies files."""
        # Create a local overlay directory (not a git repo)
        local_overlay = tmp_path / "local-config"
        local_overlay.mkdir()
        (local_overlay / "config.yaml").write_text("key: value")
        (local_overlay / "subdir").mkdir()
        (local_overlay / "subdir" / "nested.txt").write_text("nested content")

        config = {
            "version": 1,
            "overlay": {
                "repo": str(local_overlay),
                "mappings": [
                    {"src": "config.yaml", "dst": "config.yaml"},
                    {"src": "subdir/nested.txt", "dst": "nested.txt"},
                ],
            },
        }
        clone_overlay(tmp_main_repo, config)

        # Check symlinks work
        assert (tmp_main_repo / "config.yaml").is_symlink()
        assert (tmp_main_repo / "config.yaml").read_text() == "key: value"
        assert (tmp_main_repo / "nested.txt").is_symlink()
        assert (tmp_main_repo / "nested.txt").read_text() == "nested content"

    def test_clone_local_directory_without_mappings(self, tmp_main_repo, tmp_path):
        """Clone from local directory without mappings symlinks all files."""
        # Create a local overlay directory
        local_overlay = tmp_path / "local-config"
        local_overlay.mkdir()
        (local_overlay / "settings.yaml").write_text("setting: true")
        (local_overlay / "data").mkdir()
        (local_overlay / "data" / "items.json").write_text('{"items": []}')

        config = {
            "version": 1,
            "overlay": {
                "repo": str(local_overlay),
            },
        }
        clone_overlay(tmp_main_repo, config)

        # All files should be symlinked at their original paths
        assert (tmp_main_repo / "settings.yaml").is_symlink()
        assert (tmp_main_repo / "settings.yaml").read_text() == "setting: true"
        assert (tmp_main_repo / "data" / "items.json").is_symlink()
        assert (tmp_main_repo / "data" / "items.json").read_text() == '{"items": []}'

    def test_clone_local_relative_path(self, tmp_main_repo, tmp_path):
        """Clone from relative local path works."""
        # Create a sibling directory
        local_overlay = tmp_path / "sibling-config"
        local_overlay.mkdir()
        (local_overlay / "data.txt").write_text("data")

        config = {
            "version": 1,
            "overlay": {
                "repo": "../sibling-config",
                "mappings": [
                    {"src": "data.txt", "dst": "data.txt"},
                ],
            },
        }
        clone_overlay(tmp_main_repo, config)

        assert (tmp_main_repo / "data.txt").is_symlink()
        assert (tmp_main_repo / "data.txt").read_text() == "data"

    def test_clone_local_directory_not_found(self, tmp_main_repo):
        """Clone from non-existent local path errors."""
        config = {
            "version": 1,
            "overlay": {
                "repo": "/nonexistent/path",
            },
        }
        with pytest.raises(OverlayError, match="Local overlay path not found"):
            clone_overlay(tmp_main_repo, config)

    def test_symlinks_created_for_file(self, tmp_main_repo, sample_config):
        """Symlinks created for file mappings."""
        clone_overlay(tmp_main_repo, sample_config)

        env_link = tmp_main_repo / ".env"
        assert env_link.is_symlink()
        assert env_link.read_text() == "API_KEY=xxx"

    def test_symlinks_created_for_directory(self, tmp_main_repo, sample_config):
        """Symlinks created for directory mappings."""
        clone_overlay(tmp_main_repo, sample_config)

        secrets_link = tmp_main_repo / "config" / "secrets"
        assert secrets_link.is_symlink()
        assert (secrets_link / "db.yaml").read_text() == "password: secret"

    def test_symlinks_are_relative(self, tmp_main_repo, sample_config):
        """Symlinks are relative paths."""
        clone_overlay(tmp_main_repo, sample_config)

        env_link = tmp_main_repo / ".env"
        target = os.readlink(env_link)
        assert not os.path.isabs(target)
        assert target == ".repoverlay/repo/.env.production"

    def test_parent_directories_created(self, tmp_main_repo, sample_config):
        """Parent directories created as needed."""
        clone_overlay(tmp_main_repo, sample_config)

        config_dir = tmp_main_repo / "config"
        assert config_dir.is_dir()

    def test_state_written(self, tmp_main_repo, sample_config):
        """State file written after clone."""
        clone_overlay(tmp_main_repo, sample_config)

        state = read_state(tmp_main_repo)
        assert "config/secrets" in state["symlinks"]
        assert ".env" in state["symlinks"]

    def test_error_if_already_cloned(self, tmp_main_repo, sample_config):
        """Error if destination exists."""
        clone_overlay(tmp_main_repo, sample_config)

        with pytest.raises(OverlayError, match="Already cloned"):
            clone_overlay(tmp_main_repo, sample_config)

    def test_error_if_source_not_found(self, tmp_main_repo, sample_config):
        """Error if source doesn't exist in overlay."""
        sample_config["overlay"]["mappings"] = [
            {"src": "nonexistent", "dst": "foo"}
        ]

        with pytest.raises(OverlayError, match="Source not found in overlay"):
            clone_overlay(tmp_main_repo, sample_config)

    def test_skips_if_destination_exists(self, tmp_main_repo, sample_config, capsys):
        """Skips files if destination already exists (with warning)."""
        # Create the destination file first
        (tmp_main_repo / ".env").write_text("existing")

        clone_overlay(tmp_main_repo, sample_config)

        # The existing file should be preserved (not overwritten)
        assert (tmp_main_repo / ".env").read_text() == "existing"
        # It should NOT be a symlink
        assert not (tmp_main_repo / ".env").is_symlink()
        # Other symlinks should still be created
        assert (tmp_main_repo / "config" / "secrets").is_symlink()

        # Check state doesn't include skipped file
        state = read_state(tmp_main_repo)
        assert ".env" not in state["symlinks"]
        assert "config/secrets" in state["symlinks"]

    def test_force_overwrites_existing(self, tmp_main_repo, sample_config):
        """Force flag overwrites existing destination files."""
        # Create the destination file first
        (tmp_main_repo / ".env").write_text("existing")

        clone_overlay(tmp_main_repo, sample_config, force=True)

        # The file should now be a symlink with overlay content
        assert (tmp_main_repo / ".env").is_symlink()
        assert (tmp_main_repo / ".env").read_text() == "API_KEY=xxx"

    def test_checkout_ref(self, tmp_main_repo, tmp_overlay_repo, sample_config):
        """Checkout specific ref if specified."""
        import subprocess

        # Create a new branch in overlay repo
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=tmp_overlay_repo,
            check=True,
            capture_output=True,
        )
        (tmp_overlay_repo / "feature.txt").write_text("feature content")
        subprocess.run(
            ["git", "add", "."],
            cwd=tmp_overlay_repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "feature"],
            cwd=tmp_overlay_repo,
            check=True,
            capture_output=True,
        )

        # Update config to use feature branch
        sample_config["overlay"]["ref"] = "feature"
        sample_config["overlay"]["mappings"] = [
            {"src": "feature.txt", "dst": "feature.txt"}
        ]

        clone_overlay(tmp_main_repo, sample_config)

        # Verify feature file is present
        feature_link = tmp_main_repo / "feature.txt"
        assert feature_link.read_text() == "feature content"

    def test_force_flag_overwrites(self, tmp_main_repo, sample_config):
        """Force flag allows overwriting existing repo."""
        clone_overlay(tmp_main_repo, sample_config)

        # Should succeed with force=True
        clone_overlay(tmp_main_repo, sample_config, force=True)

        # Verify symlinks still work
        assert (tmp_main_repo / ".env").read_text() == "API_KEY=xxx"

    def test_force_clone_blocked_with_unpushed_commits(self, tmp_main_repo, sample_config):
        """Force clone is blocked when there are unpushed commits."""
        clone_overlay(tmp_main_repo, sample_config)

        repo_dir = get_repo_dir(tmp_main_repo)

        # Make a commit in the overlay repo (will be unpushed)
        (repo_dir / "newfile.txt").write_text("new content")
        subprocess.run(["git", "add", "newfile.txt"], cwd=repo_dir, check=True)
        subprocess.run(
            ["git", "commit", "-m", "unpushed commit"],
            cwd=repo_dir,
            check=True,
        )

        # Force clone should be blocked
        with pytest.raises(UnpushedCommitsError) as exc_info:
            clone_overlay(tmp_main_repo, sample_config, force=True)

        assert "unpushed commit" in str(exc_info.value)
        assert exc_info.value.commit_count == 1

    def test_force_clone_blocked_with_uncommitted_changes(self, tmp_main_repo, sample_config):
        """Force clone is blocked when there are uncommitted changes."""
        clone_overlay(tmp_main_repo, sample_config)

        repo_dir = get_repo_dir(tmp_main_repo)

        # Make uncommitted changes in the overlay repo
        (repo_dir / ".env.production").write_text("modified content")

        # Force clone should be blocked
        with pytest.raises(UncommittedChangesError) as exc_info:
            clone_overlay(tmp_main_repo, sample_config, force=True)

        assert "uncommitted changes" in str(exc_info.value).lower()

    def test_dry_run_no_changes(self, tmp_main_repo, sample_config):
        """Dry run doesn't make changes."""
        output = Output(quiet=True)
        clone_overlay(tmp_main_repo, sample_config, dry_run=True, output=output)

        # Repo should not be created
        assert not get_repo_dir(tmp_main_repo).exists()

    def test_ignore_patterns_filter(self, tmp_main_repo, sample_config):
        """Ignore patterns filter out mappings."""
        # Add ignore file
        (tmp_main_repo / ".repoverlayignore").write_text(".env.production\n")

        clone_overlay(tmp_main_repo, sample_config)

        # .env should not be created (filtered by ignore)
        assert not (tmp_main_repo / ".env").exists()
        # secrets should still be created
        assert (tmp_main_repo / "config" / "secrets").exists()

    def test_created_directories_tracked(self, tmp_main_repo, sample_config):
        """Created directories are tracked in state."""
        clone_overlay(tmp_main_repo, sample_config)

        state = read_state(tmp_main_repo)
        assert "config" in state.get("created_directories", [])


class TestSyncOverlay:
    """Tests for sync_overlay function."""

    def test_sync_removes_old_symlinks(self, tmp_main_repo, sample_config):
        """Sync removes symlinks no longer in config."""
        clone_overlay(tmp_main_repo, sample_config)

        # Modify config to remove .env mapping
        sample_config["overlay"]["mappings"] = [
            {"src": "secrets", "dst": "config/secrets"},
        ]

        output = Output(quiet=True)
        sync_overlay(tmp_main_repo, sample_config, output=output)

        # .env symlink should be removed
        assert not (tmp_main_repo / ".env").exists()
        # secrets should still exist
        assert (tmp_main_repo / "config" / "secrets").exists()

    def test_sync_creates_new_symlinks(self, tmp_main_repo, tmp_overlay_repo, sample_config):
        """Sync creates new symlinks from updated config."""
        clone_overlay(tmp_main_repo, sample_config)

        # Add a new file to the cloned overlay repo (simulating a git pull)
        repo_dir = get_repo_dir(tmp_main_repo)
        (repo_dir / "new.txt").write_text("new content")

        # Add to config
        sample_config["overlay"]["mappings"].append(
            {"src": "new.txt", "dst": "new.txt"}
        )

        output = Output(quiet=True)
        sync_overlay(tmp_main_repo, sample_config, output=output)

        # New symlink should exist
        assert (tmp_main_repo / "new.txt").is_symlink()

    def test_sync_removes_orphaned_symlinks(self, tmp_main_repo, tmp_overlay_repo, sample_config):
        """Sync removes symlinks whose targets no longer exist."""
        clone_overlay(tmp_main_repo, sample_config)

        # Remove source file from overlay
        (get_repo_dir(tmp_main_repo) / ".env.production").unlink()

        output = Output(quiet=True)
        sync_overlay(tmp_main_repo, sample_config, output=output)

        # Orphaned symlink should be removed
        assert not (tmp_main_repo / ".env").exists()

    def test_sync_dry_run(self, tmp_main_repo, sample_config):
        """Sync dry run doesn't make changes."""
        clone_overlay(tmp_main_repo, sample_config)

        # Modify config to remove one mapping
        sample_config["overlay"]["mappings"] = [
            {"src": "secrets", "dst": "config/secrets"},
        ]

        output = Output(quiet=True)
        sync_overlay(tmp_main_repo, sample_config, dry_run=True, output=output)

        # .env symlink should still exist (dry run doesn't remove it)
        assert (tmp_main_repo / ".env").exists()

    def test_sync_force_overwrites(self, tmp_main_repo, sample_config):
        """Sync with force overwrites existing files."""
        clone_overlay(tmp_main_repo, sample_config)

        # Remove symlink and create regular file
        (tmp_main_repo / ".env").unlink()
        (tmp_main_repo / ".env").write_text("regular file")

        output = Output(quiet=True)
        sync_overlay(tmp_main_repo, sample_config, force=True, output=output)

        # Should be a symlink again
        assert (tmp_main_repo / ".env").is_symlink()

    def test_sync_without_mappings(self, tmp_main_repo, tmp_overlay_repo):
        """Sync without mappings uses all files from overlay."""
        # First clone with explicit mappings
        config = {
            "version": 1,
            "overlay": {
                "repo": str(tmp_overlay_repo),
                "mappings": [
                    {"src": ".env.production", "dst": ".env"},
                ],
            },
        }
        clone_overlay(tmp_main_repo, config)

        # Now sync without mappings - should add all files
        config_no_mappings = {
            "version": 1,
            "overlay": {
                "repo": str(tmp_overlay_repo),
            },
        }
        output = Output(quiet=True)
        sync_overlay(tmp_main_repo, config_no_mappings, output=output)

        # All files from overlay should now be symlinked
        assert (tmp_main_repo / ".env.production").is_symlink()
        assert (tmp_main_repo / "secrets" / "db.yaml").is_symlink()

    def test_sync_with_local_directory(self, tmp_main_repo, tmp_path):
        """Sync works with local directory overlay."""
        # Create a local overlay
        local_overlay = tmp_path / "local-config"
        local_overlay.mkdir()
        (local_overlay / "app.conf").write_text("app config")

        config = {
            "version": 1,
            "overlay": {
                "repo": str(local_overlay),
            },
        }
        clone_overlay(tmp_main_repo, config)

        # Add a new file to the local overlay
        (local_overlay / "new.conf").write_text("new config")

        # Sync should pick up the new file (after copying to repo dir)
        # Note: for local dirs, we'd need to re-clone to get new files
        # This test verifies sync works with existing files
        output = Output(quiet=True)
        sync_overlay(tmp_main_repo, config, output=output)

        assert (tmp_main_repo / "app.conf").is_symlink()

    def test_sync_skips_existing_files(self, tmp_main_repo, tmp_overlay_repo, sample_config):
        """Sync skips files where destination already exists."""
        output = Output(quiet=True)
        clone_overlay(tmp_main_repo, sample_config, output=output)

        # Add a new file to the cloned overlay repo
        repo_dir = get_repo_dir(tmp_main_repo)
        (repo_dir / "new.txt").write_text("new content")

        # Create a conflicting file in main repo
        (tmp_main_repo / "conflict.txt").write_text("existing content")

        # Add both to config
        sample_config["overlay"]["mappings"].append(
            {"src": "new.txt", "dst": "new.txt"}
        )
        sample_config["overlay"]["mappings"].append(
            {"src": "new.txt", "dst": "conflict.txt"}
        )

        sync_overlay(tmp_main_repo, sample_config, output=output)

        # new.txt should be symlinked
        assert (tmp_main_repo / "new.txt").is_symlink()
        # conflict.txt should be preserved (not a symlink)
        assert not (tmp_main_repo / "conflict.txt").is_symlink()
        assert (tmp_main_repo / "conflict.txt").read_text() == "existing content"

    def test_sync_force_overwrites_existing(self, tmp_main_repo, tmp_overlay_repo, sample_config):
        """Sync with force overwrites existing files."""
        output = Output(quiet=True)
        clone_overlay(tmp_main_repo, sample_config, output=output)

        # Add a new file to the cloned overlay repo
        repo_dir = get_repo_dir(tmp_main_repo)
        (repo_dir / "new.txt").write_text("overlay content")

        # Create a conflicting file in main repo
        (tmp_main_repo / "conflict.txt").write_text("existing content")

        # Add mapping for the conflict
        sample_config["overlay"]["mappings"].append(
            {"src": "new.txt", "dst": "conflict.txt"}
        )

        sync_overlay(tmp_main_repo, sample_config, force=True, output=output)

        # conflict.txt should now be a symlink with overlay content
        assert (tmp_main_repo / "conflict.txt").is_symlink()
        assert (tmp_main_repo / "conflict.txt").read_text() == "overlay content"


class TestUnlinkOverlay:
    """Tests for unlink_overlay function."""

    def test_unlink_after_add_and_sync(self, tmp_main_repo, tmp_overlay_repo):
        """Unlink removes symlinks for files added after initial clone.

        Reproduces bug: clone (no mappings) -> add new file to repo -> sync -> unlink
        should remove ALL symlinks including ones for newly added files.
        """
        # Clone without explicit mappings - symlinks auto-generated for all files
        config = {
            "version": 1,
            "overlay": {
                "repo": str(tmp_overlay_repo),
            },
        }
        output = Output(quiet=True)
        clone_overlay(tmp_main_repo, config, output=output)

        # Verify initial symlinks
        assert (tmp_main_repo / ".env.production").is_symlink()
        assert (tmp_main_repo / "secrets" / "db.yaml").is_symlink()

        # Add a new file to the cloned overlay repo
        # (simulates a file appearing in the repo, e.g. after pull or repoverlay add)
        repo_dir = get_repo_dir(tmp_main_repo)
        (repo_dir / "newfile.txt").write_text("new content")

        # Sync to pick up the new file (this is what pull does after fetching)
        sync_overlay(tmp_main_repo, config, output=output)

        # The new file should now be symlinked
        assert (tmp_main_repo / "newfile.txt").is_symlink()
        assert (tmp_main_repo / "newfile.txt").read_text() == "new content"

        # Verify state includes the new symlink
        state = read_state(tmp_main_repo)
        assert "newfile.txt" in state["symlinks"], (
            f"newfile.txt not tracked in state! State symlinks: {state['symlinks']}"
        )

        # Now unlink (force to bypass uncommitted changes check)
        unlink_overlay(tmp_main_repo, force=True, output=output)

        # Verify ALL symlinks are gone, including the newly added one
        assert not (tmp_main_repo / ".env.production").is_symlink(), \
            ".env.production symlink was not removed by unlink"
        assert not (tmp_main_repo / "secrets" / "db.yaml").is_symlink(), \
            "secrets/db.yaml symlink was not removed by unlink"
        assert not (tmp_main_repo / "newfile.txt").exists(), \
            "newfile.txt symlink was not removed by unlink - state not updated after add+sync!"

    def test_unlink_after_new_files_added_to_repo_and_synced(self, tmp_main_repo, tmp_overlay_repo):
        """Unlink must remove symlinks for files added to repo after clone.

        Scenario: clone (no mappings) -> new file appears in repo (via add/pull) ->
        sync creates symlink -> unlink should remove it.
        Bug: sync creates symlinks for new files but doesn't track them in state,
        so unlink leaves dangling symlinks behind.
        """
        config = {
            "version": 1,
            "overlay": {
                "repo": str(tmp_overlay_repo),
            },
        }
        output = Output(quiet=True)

        # Step 1: Clone - creates symlinks for initial files
        clone_overlay(tmp_main_repo, config, output=output)
        repo_dir = get_repo_dir(tmp_main_repo)

        initial_state = read_state(tmp_main_repo)
        assert ".env.production" in initial_state["symlinks"]
        assert "secrets/db.yaml" in initial_state["symlinks"]

        # Step 2: New files appear in the repo (simulates add+commit or pull)
        (repo_dir / "newconfig.yaml").write_text("db_host: localhost")
        (repo_dir / "deploy" / "settings.ini").parent.mkdir(parents=True, exist_ok=True)
        (repo_dir / "deploy" / "settings.ini").write_text("[deploy]\nenv=prod")

        # Step 3: Sync picks up new files and creates symlinks
        sync_overlay(tmp_main_repo, config, output=output)

        # Verify new symlinks were created
        assert (tmp_main_repo / "newconfig.yaml").is_symlink()
        assert (tmp_main_repo / "deploy" / "settings.ini").is_symlink()

        # KEY CHECK: Are the new symlinks tracked in state?
        state_after_sync = read_state(tmp_main_repo)
        assert "newconfig.yaml" in state_after_sync["symlinks"], \
            f"newconfig.yaml missing from state! symlinks={state_after_sync['symlinks']}"
        assert "deploy/settings.ini" in state_after_sync["symlinks"], \
            f"deploy/settings.ini missing from state! symlinks={state_after_sync['symlinks']}"

        # Step 4: Unlink should remove ALL symlinks
        unlink_overlay(tmp_main_repo, force=True, output=output)

        # Nothing should be left as a symlink
        assert not (tmp_main_repo / ".env.production").is_symlink(), \
            ".env.production not cleaned up"
        assert not (tmp_main_repo / "secrets" / "db.yaml").is_symlink(), \
            "secrets/db.yaml not cleaned up"
        assert not (tmp_main_repo / "newconfig.yaml").exists(), \
            "newconfig.yaml symlink left behind by unlink!"
        assert not (tmp_main_repo / "deploy" / "settings.ini").exists(), \
            "deploy/settings.ini symlink left behind by unlink!"

    def test_unlink_after_multiple_syncs_with_new_files(self, tmp_main_repo, tmp_overlay_repo):
        """Unlink removes all symlinks after multiple syncs add new files.

        Tests: clone -> sync -> add files -> sync -> unlink. Verifies that
        symlinks created across multiple sync cycles are all tracked in state.
        """
        config = {
            "version": 1,
            "overlay": {
                "repo": str(tmp_overlay_repo),
            },
        }
        output = Output(quiet=True)
        clone_overlay(tmp_main_repo, config, output=output)
        repo_dir = get_repo_dir(tmp_main_repo)

        # First sync (no-op, same files)
        sync_overlay(tmp_main_repo, config, output=output)

        # Add new files to the repo at different times and sync each time
        (repo_dir / "file1.txt").write_text("content 1")
        sync_overlay(tmp_main_repo, config, output=output)
        assert (tmp_main_repo / "file1.txt").is_symlink()

        (repo_dir / "file2.txt").write_text("content 2")
        (repo_dir / "subdir").mkdir(exist_ok=True)
        (repo_dir / "subdir" / "file3.txt").write_text("content 3")
        sync_overlay(tmp_main_repo, config, output=output)
        assert (tmp_main_repo / "file2.txt").is_symlink()
        assert (tmp_main_repo / "subdir" / "file3.txt").is_symlink()

        # Verify ALL symlinks are in state
        state = read_state(tmp_main_repo)
        symlinks = set(state["symlinks"])
        for expected in [".env.production", "secrets/db.yaml", "file1.txt", "file2.txt", "subdir/file3.txt"]:
            assert expected in symlinks, (
                f"{expected} not tracked in state! State: {symlinks}"
            )

        # Unlink
        unlink_overlay(tmp_main_repo, force=True, output=output)

        # ALL symlinks should be gone
        assert not (tmp_main_repo / ".env.production").is_symlink()
        assert not (tmp_main_repo / "secrets" / "db.yaml").is_symlink()
        assert not (tmp_main_repo / "file1.txt").exists()
        assert not (tmp_main_repo / "file2.txt").exists()
        assert not (tmp_main_repo / "subdir" / "file3.txt").exists()

    def test_unlink_removes_symlinks(self, tmp_main_repo, sample_config):
        """Unlink removes all symlinks."""
        clone_overlay(tmp_main_repo, sample_config)

        output = Output(quiet=True)
        unlink_overlay(tmp_main_repo, output=output)

        assert not (tmp_main_repo / ".env").exists()
        assert not (tmp_main_repo / "config" / "secrets").exists()

    def test_unlink_removes_empty_directories(self, tmp_main_repo, sample_config):
        """Unlink removes created directories if empty."""
        clone_overlay(tmp_main_repo, sample_config)

        output = Output(quiet=True)
        unlink_overlay(tmp_main_repo, output=output)

        # config/ should be removed (was empty after removing symlink)
        assert not (tmp_main_repo / "config").exists()

    def test_unlink_keeps_nonempty_directories(self, tmp_main_repo, sample_config):
        """Unlink keeps directories that have other files."""
        clone_overlay(tmp_main_repo, sample_config)

        # Add a file to config/
        (tmp_main_repo / "config" / "other.txt").write_text("keep me")

        output = Output(quiet=True)
        unlink_overlay(tmp_main_repo, output=output)

        # config/ should still exist (has other file)
        assert (tmp_main_repo / "config").exists()
        assert (tmp_main_repo / "config" / "other.txt").exists()

    def test_unlink_with_remove_repo(self, tmp_main_repo, sample_config):
        """Unlink with remove_repo removes .repoverlay/."""
        clone_overlay(tmp_main_repo, sample_config)

        output = Output(quiet=True)
        unlink_overlay(tmp_main_repo, remove_repo=True, output=output)

        assert not get_overlay_dir(tmp_main_repo).exists()

    def test_unlink_dry_run(self, tmp_main_repo, sample_config):
        """Unlink dry run doesn't remove anything."""
        clone_overlay(tmp_main_repo, sample_config)

        output = Output(quiet=True)
        unlink_overlay(tmp_main_repo, dry_run=True, output=output)

        # Everything should still exist
        assert (tmp_main_repo / ".env").exists()
        assert get_overlay_dir(tmp_main_repo).exists()

    def test_unlink_blocks_on_unpushed_commits(self, tmp_main_repo, sample_config):
        """Unlink fails if there are unpushed commits."""
        clone_overlay(tmp_main_repo, sample_config)

        repo_dir = get_repo_dir(tmp_main_repo)

        # Configure git user for commits
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )

        # Make an unpushed commit
        (repo_dir / "new_file.txt").write_text("new content")
        subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "unpushed commit"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )

        output = Output(quiet=True)
        with pytest.raises(UnpushedCommitsError, match="unpushed commit"):
            unlink_overlay(tmp_main_repo, output=output)

    def test_unlink_warns_on_uncommitted_changes(self, tmp_main_repo, sample_config):
        """Unlink warns if there are uncommitted changes."""
        clone_overlay(tmp_main_repo, sample_config)

        repo_dir = get_repo_dir(tmp_main_repo)

        # Create uncommitted changes
        (repo_dir / "untracked.txt").write_text("untracked content")

        output = Output(quiet=True)
        with pytest.raises(UncommittedChangesError, match="Uncommitted changes"):
            unlink_overlay(tmp_main_repo, output=output)

    def test_unlink_force_bypasses_uncommitted_warning(self, tmp_main_repo, sample_config):
        """Unlink with force bypasses uncommitted changes warning."""
        clone_overlay(tmp_main_repo, sample_config)

        repo_dir = get_repo_dir(tmp_main_repo)

        # Create uncommitted changes
        (repo_dir / "untracked.txt").write_text("untracked content")

        output = Output(quiet=True)
        # Should not raise with force=True
        unlink_overlay(tmp_main_repo, force=True, output=output)

        # Symlinks should be removed
        assert not (tmp_main_repo / ".env").exists()

    def test_unlink_resumable_when_repo_missing(self, tmp_main_repo, sample_config):
        """Unlink can resume when repo is already removed but state exists."""
        import shutil

        clone_overlay(tmp_main_repo, sample_config)

        # Simulate interrupted unlink - remove repo but keep state
        repo_dir = get_repo_dir(tmp_main_repo)
        shutil.rmtree(repo_dir)

        # State should still have symlinks
        state = read_state(tmp_main_repo)
        assert len(state.get("symlinks", [])) > 0

        # Symlinks still exist
        assert (tmp_main_repo / ".env").is_symlink()

        output = Output(quiet=True)
        # Should not raise, should continue cleaning up
        unlink_overlay(tmp_main_repo, output=output)

        # Symlinks should now be removed
        assert not (tmp_main_repo / ".env").exists()

    def test_unlink_dry_run_skips_validation(self, tmp_main_repo, sample_config):
        """Unlink dry run doesn't fail on uncommitted changes."""
        clone_overlay(tmp_main_repo, sample_config)

        repo_dir = get_repo_dir(tmp_main_repo)

        # Create uncommitted changes
        (repo_dir / "untracked.txt").write_text("untracked content")

        output = Output(quiet=True)
        # Should not raise with dry_run=True
        unlink_overlay(tmp_main_repo, dry_run=True, output=output)

        # Everything should still exist
        assert (tmp_main_repo / ".env").exists()
