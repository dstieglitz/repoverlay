"""Tests for pull/fetch consistency with overlay repo operations.

Ensures that state (symlinks, state.json) stays consistent across various
scenarios: remote changes, local modifications, add/commit before pull, etc.
"""

import subprocess
import sys

import pytest
import yaml

from repoverlay.output import Output
from repoverlay.overlay import get_repo_dir
from repoverlay.state import read_state


@pytest.fixture
def overlay_origin(tmp_path):
    """Non-bare local git repo acting as the overlay origin.

    Returns the repo path. This is the repo repoverlay will clone from.
    Changes made here can be pulled via repoverlay pull.
    """
    repo = tmp_path / "overlay-origin"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo, check=True, capture_output=True,
    )
    # Allow receiving pushes to checked-out branch (needed for repoverlay push)
    subprocess.run(
        ["git", "config", "receive.denyCurrentBranch", "updateInstead"],
        cwd=repo, check=True, capture_output=True,
    )

    # Create initial files
    (repo / "secrets").mkdir()
    (repo / "secrets" / "db.yaml").write_text("password: secret")
    (repo / ".env.production").write_text("API_KEY=xxx")

    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo, check=True, capture_output=True,
    )
    return repo


@pytest.fixture
def project_with_overlay(tmp_path, overlay_origin):
    """A main project with repoverlay cloned from overlay_origin.

    Returns (main_repo, overlay_origin, config).
    """
    main = tmp_path / "main"
    main.mkdir()
    subprocess.run(["git", "init"], cwd=main, check=True, capture_output=True)

    config = {
        "version": 1,
        "overlay": {
            "repo": str(overlay_origin),
        },
    }
    config_path = main / ".repoverlay.yaml"
    config_path.write_text(yaml.dump(config))

    # Clone via repoverlay
    result = subprocess.run(
        [sys.executable, "-m", "repoverlay", "clone"],
        cwd=main, capture_output=True, text=True,
    )
    assert result.returncode == 0, f"Clone failed: {result.stderr}"

    # Configure git user in the overlay repo for local commits
    repo_dir = main / ".repoverlay" / "repo"
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo_dir, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo_dir, check=True, capture_output=True,
    )

    return main, overlay_origin, config


def push_to_origin(origin, filename, content, commit_msg):
    """Helper: create/modify a file in the origin repo and commit it."""
    from pathlib import Path
    filepath = Path(origin) / filename
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(content)
    subprocess.run(["git", "add", "."], cwd=origin, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", commit_msg],
        cwd=origin, check=True, capture_output=True,
    )


def delete_in_origin(origin, filename, commit_msg):
    """Helper: delete a file in the origin repo and commit."""
    from pathlib import Path
    filepath = Path(origin) / filename
    filepath.unlink()
    subprocess.run(["git", "add", "."], cwd=origin, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", commit_msg],
        cwd=origin, check=True, capture_output=True,
    )


class TestPullNewFiles:
    """Test pulling new files from origin and verifying symlink state."""

    def test_pull_adds_new_file_symlink(self, project_with_overlay):
        """New file committed to origin appears as symlink after pull."""
        main, origin, config = project_with_overlay

        push_to_origin(origin, "newconfig.yaml", "host: localhost", "add config")

        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "pull"],
            cwd=main, capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Pull failed: {result.stderr}"

        assert (main / "newconfig.yaml").is_symlink()
        assert (main / "newconfig.yaml").read_text() == "host: localhost"

        state = read_state(main)
        assert "newconfig.yaml" in state["symlinks"]

    def test_pull_adds_nested_file_symlink(self, project_with_overlay):
        """New nested file in origin appears as symlink after pull."""
        main, origin, config = project_with_overlay

        push_to_origin(
            origin, "deploy/prod/values.yaml",
            "replicas: 3", "add deploy config",
        )

        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "pull"],
            cwd=main, capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Pull failed: {result.stderr}"

        assert (main / "deploy" / "prod" / "values.yaml").is_symlink()
        assert (main / "deploy" / "prod" / "values.yaml").read_text() == "replicas: 3"

        state = read_state(main)
        assert "deploy/prod/values.yaml" in state["symlinks"]

    def test_pull_multiple_new_files(self, project_with_overlay):
        """Multiple new files committed to origin all get symlinks after pull."""
        main, origin, config = project_with_overlay

        from pathlib import Path
        (Path(origin) / "file_a.txt").write_text("aaa")
        (Path(origin) / "file_b.txt").write_text("bbb")
        (Path(origin) / "dir").mkdir(exist_ok=True)
        (Path(origin) / "dir" / "file_c.txt").write_text("ccc")
        subprocess.run(["git", "add", "."], cwd=origin, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add many files"],
            cwd=origin, check=True, capture_output=True,
        )

        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "pull"],
            cwd=main, capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Pull failed: {result.stderr}"

        assert (main / "file_a.txt").is_symlink()
        assert (main / "file_b.txt").is_symlink()
        assert (main / "dir" / "file_c.txt").is_symlink()

        state = read_state(main)
        for f in ["file_a.txt", "file_b.txt", "dir/file_c.txt"]:
            assert f in state["symlinks"], f"{f} not in state"


class TestPullModifiedFiles:
    """Test pulling modified files preserves symlink integrity."""

    def test_pull_modified_file_content_updates(self, project_with_overlay):
        """Modified file in origin is reflected through existing symlink after pull."""
        main, origin, config = project_with_overlay

        # Verify initial content
        assert (main / "secrets" / "db.yaml").is_symlink()
        assert (main / "secrets" / "db.yaml").read_text() == "password: secret"

        # Modify file in origin
        push_to_origin(
            origin, "secrets/db.yaml",
            "password: new_secret", "update secret",
        )

        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "pull"],
            cwd=main, capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Pull failed: {result.stderr}"

        # Symlink still works and shows new content
        assert (main / "secrets" / "db.yaml").is_symlink()
        assert (main / "secrets" / "db.yaml").read_text() == "password: new_secret"

    def test_pull_modified_file_state_unchanged(self, project_with_overlay):
        """State should remain consistent after pulling modified files."""
        main, origin, config = project_with_overlay

        state_before = read_state(main)

        push_to_origin(
            origin, ".env.production",
            "API_KEY=new_key", "update env",
        )

        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "pull"],
            cwd=main, capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Pull failed: {result.stderr}"

        state_after = read_state(main)
        # Symlinks list should be identical (same files, just content changed)
        assert set(state_before["symlinks"]) == set(state_after["symlinks"])


class TestPullDeletedFiles:
    """Test pulling deleted files cleans up symlinks."""

    def test_pull_deleted_file_removes_symlink(self, project_with_overlay):
        """File deleted in origin has its symlink removed after pull."""
        main, origin, config = project_with_overlay

        assert (main / ".env.production").is_symlink()

        delete_in_origin(origin, ".env.production", "remove env file")

        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "pull"],
            cwd=main, capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Pull failed: {result.stderr}"

        # Orphaned symlink should be removed by sync
        assert not (main / ".env.production").is_symlink()

        state = read_state(main)
        assert ".env.production" not in state["symlinks"]

    def test_pull_deleted_directory_cleans_up(self, project_with_overlay):
        """Directory deleted in origin has its symlinks removed after pull."""
        main, origin, config = project_with_overlay

        assert (main / "secrets" / "db.yaml").is_symlink()

        # Delete the secrets directory in origin
        import shutil
        shutil.rmtree(origin / "secrets")
        subprocess.run(["git", "add", "."], cwd=origin, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "remove secrets dir"],
            cwd=origin, check=True, capture_output=True,
        )

        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "pull"],
            cwd=main, capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Pull failed: {result.stderr}"

        assert not (main / "secrets" / "db.yaml").is_symlink()

        state = read_state(main)
        assert "secrets/db.yaml" not in state["symlinks"]


class TestPullWithLocalChanges:
    """Test pull behavior with local uncommitted/committed changes."""

    def test_pull_with_uncommitted_local_changes_to_different_file(self, project_with_overlay):
        """Pull preserves local uncommitted changes to different files."""
        main, origin, config = project_with_overlay
        repo_dir = main / ".repoverlay" / "repo"

        # Make local uncommitted change
        (repo_dir / ".env.production").write_text("API_KEY=local_change")

        # Push a change to a different file in origin
        push_to_origin(origin, "newfile.txt", "remote content", "add new file")

        # Pull - may fail due to uncommitted changes, that's OK
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "pull"],
            cwd=main, capture_output=True, text=True,
        )

        # Local change should be preserved regardless
        assert (repo_dir / ".env.production").read_text() == "API_KEY=local_change"

    def test_pull_with_committed_unpushed_changes_ff(self, project_with_overlay):
        """Pull succeeds (fast-forward) when only remote has new commits."""
        main, origin, config = project_with_overlay

        # Push a change to origin
        push_to_origin(origin, "remote_file.txt", "remote content", "remote change")

        # Pull should fast-forward
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "pull"],
            cwd=main, capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Pull failed: {result.stderr}"

        assert (main / "remote_file.txt").is_symlink()
        assert (main / "remote_file.txt").read_text() == "remote content"


class TestPullWithLocalCommitsBeforePull:
    """Test pulling when user has committed locally before pulling remote changes."""

    def test_local_commit_then_pull_no_remote_changes(self, project_with_overlay):
        """Local commit + pull (no remote changes) = no conflict."""
        main, origin, config = project_with_overlay
        repo_dir = main / ".repoverlay" / "repo"

        # Commit locally
        (repo_dir / "local_new.txt").write_text("local content")
        subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "local commit"],
            cwd=repo_dir, check=True, capture_output=True,
        )

        # Pull (no remote changes)
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "pull"],
            cwd=main, capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Pull failed: {result.stderr}"

        # Local file should have a symlink (sync after pull)
        assert (main / "local_new.txt").is_symlink()

        state = read_state(main)
        assert "local_new.txt" in state["symlinks"]

    def test_local_commit_and_remote_commit_rebase(self, project_with_overlay):
        """Local + remote commits resolved with --rebase."""
        main, origin, config = project_with_overlay
        repo_dir = main / ".repoverlay" / "repo"

        # Commit locally (different file than remote will change)
        (repo_dir / "local_file.txt").write_text("local content")
        subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "local commit"],
            cwd=repo_dir, check=True, capture_output=True,
        )

        # Push a different file to origin
        push_to_origin(origin, "remote_file.txt", "remote content", "remote commit")

        # Pull with rebase
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "pull", "--rebase"],
            cwd=main, capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Pull --rebase failed: {result.stderr}"

        # Both files should be symlinked
        assert (main / "local_file.txt").is_symlink()
        assert (main / "remote_file.txt").is_symlink()
        assert (main / "local_file.txt").read_text() == "local content"
        assert (main / "remote_file.txt").read_text() == "remote content"

        state = read_state(main)
        assert "local_file.txt" in state["symlinks"]
        assert "remote_file.txt" in state["symlinks"]

    def test_local_commit_and_remote_commit_merge(self, project_with_overlay):
        """Local + remote commits resolved with --merge."""
        main, origin, config = project_with_overlay
        repo_dir = main / ".repoverlay" / "repo"

        # Commit locally
        (repo_dir / "local_merge.txt").write_text("local merge content")
        subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "local for merge"],
            cwd=repo_dir, check=True, capture_output=True,
        )

        # Push a different file to origin
        push_to_origin(origin, "remote_merge.txt", "remote merge content", "remote for merge")

        # Pull with merge
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "pull", "--merge"],
            cwd=main, capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Pull --merge failed: {result.stderr}"

        assert (main / "local_merge.txt").is_symlink()
        assert (main / "remote_merge.txt").is_symlink()

        state = read_state(main)
        assert "local_merge.txt" in state["symlinks"]
        assert "remote_merge.txt" in state["symlinks"]

    def test_divergent_branches_without_strategy_gives_helpful_error(self, project_with_overlay):
        """Divergent branches without strategy gives helpful error message."""
        main, origin, config = project_with_overlay
        repo_dir = main / ".repoverlay" / "repo"

        # Commit locally
        (repo_dir / "local_diverge.txt").write_text("local")
        subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "local diverge"],
            cwd=repo_dir, check=True, capture_output=True,
        )

        # Commit in origin
        push_to_origin(origin, "remote_diverge.txt", "remote", "remote diverge")

        # Pull without specifying strategy
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "pull"],
            cwd=main, capture_output=True, text=True,
        )
        # Depending on git config, may succeed or fail with divergent error
        if result.returncode != 0:
            assert (
                "divergent" in result.stderr.lower()
                or "rebase" in result.stderr.lower()
                or "merge" in result.stderr.lower()
            ), f"Unhelpful error: {result.stderr}"


class TestAddBeforePull:
    """Test adding files to overlay repo before pulling remote changes."""

    def test_add_file_then_pull_new_remote_files(self, project_with_overlay):
        """Add a file locally, commit, then pull new files from origin."""
        main, origin, config = project_with_overlay
        repo_dir = main / ".repoverlay" / "repo"

        # Add a file locally via repoverlay add
        local_file = main / "myconfig" / "settings.yaml"
        local_file.parent.mkdir(parents=True)
        local_file.write_text("key: value")

        add_result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "add", str(local_file)],
            cwd=main, capture_output=True, text=True,
        )
        assert add_result.returncode == 0, f"Add failed: {add_result.stderr}"

        # Commit the added file
        subprocess.run(
            [sys.executable, "-m", "repoverlay", "commit", "-m", "add local config"],
            cwd=main, capture_output=True, text=True,
        )

        # Push a new file to origin
        push_to_origin(origin, "remote_new.txt", "from remote", "remote new file")

        # Pull with rebase (we have local commits)
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "pull", "--rebase"],
            cwd=main, capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Pull failed: {result.stderr}"

        # Both the locally added file and remote file should be in the repo
        assert (repo_dir / "myconfig" / "settings.yaml").exists()
        assert (repo_dir / "remote_new.txt").exists()

        # Remote file should be symlinked
        assert (main / "remote_new.txt").is_symlink()

        state = read_state(main)
        assert "remote_new.txt" in state["symlinks"]

    def test_add_staged_file_then_pull_different_file(self, project_with_overlay):
        """Staged but uncommitted file preserved after pull of different file."""
        main, origin, config = project_with_overlay
        repo_dir = main / ".repoverlay" / "repo"

        # Stage a new file (don't commit)
        (repo_dir / "staged_file.txt").write_text("staged content")
        subprocess.run(["git", "add", "staged_file.txt"], cwd=repo_dir, check=True, capture_output=True)

        # Push a different file to origin
        push_to_origin(origin, "remote_pull.txt", "remote pull content", "remote for pull")

        # Pull - may or may not succeed depending on git behavior with staged changes
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "pull"],
            cwd=main, capture_output=True, text=True,
        )

        # Staged file should still exist regardless of pull outcome
        assert (repo_dir / "staged_file.txt").exists()
        assert (repo_dir / "staged_file.txt").read_text() == "staged content"


class TestCommitBeforePull:
    """Test committing files before pulling remote changes."""

    def test_commit_then_pull_with_rebase(self, project_with_overlay):
        """Commit locally then pull with rebase preserves both changes."""
        main, origin, config = project_with_overlay
        repo_dir = main / ".repoverlay" / "repo"

        # Modify and commit locally
        (repo_dir / "secrets" / "db.yaml").write_text("password: local_updated")
        subprocess.run(
            [sys.executable, "-m", "repoverlay", "commit", "-a", "-m", "local update"],
            cwd=main, capture_output=True, text=True,
        )

        # Push a different file to origin
        push_to_origin(origin, "remote_config.txt", "remote config data", "add remote config")

        # Pull with rebase
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "pull", "--rebase"],
            cwd=main, capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Pull failed: {result.stderr}"

        # Local changes preserved
        assert (main / "secrets" / "db.yaml").read_text() == "password: local_updated"
        # Remote changes applied
        assert (main / "remote_config.txt").is_symlink()
        assert (main / "remote_config.txt").read_text() == "remote config data"

        state = read_state(main)
        assert "secrets/db.yaml" in state["symlinks"]
        assert "remote_config.txt" in state["symlinks"]

    def test_commit_push_then_pull_remote_additions(self, project_with_overlay):
        """Commit and push locally, then pull after origin adds files."""
        main, origin, config = project_with_overlay
        repo_dir = main / ".repoverlay" / "repo"

        # Commit and push locally
        (repo_dir / "local_pushed.txt").write_text("pushed content")
        subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "local push"],
            cwd=repo_dir, check=True, capture_output=True,
        )

        # Push via repoverlay
        push_result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "push"],
            cwd=main, capture_output=True, text=True,
        )
        assert push_result.returncode == 0, f"Push failed: {push_result.stderr}"

        # Now add more files in origin
        push_to_origin(origin, "after_local_push.txt", "after push content", "after local push")

        # Pull should fast-forward
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "pull"],
            cwd=main, capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Pull failed: {result.stderr}"

        # Both files present
        assert (repo_dir / "local_pushed.txt").exists()
        assert (main / "after_local_push.txt").is_symlink()

        state = read_state(main)
        assert "after_local_push.txt" in state["symlinks"]
        assert "local_pushed.txt" in state["symlinks"]


class TestFetchThenPull:
    """Test fetch/pull workflow."""

    def test_fetch_then_pull(self, project_with_overlay):
        """Fetch followed by pull works correctly."""
        main, origin, config = project_with_overlay

        push_to_origin(origin, "fetched_file.txt", "fetch content", "for fetch test")

        # Fetch first
        fetch_result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "fetch"],
            cwd=main, capture_output=True, text=True,
        )
        assert fetch_result.returncode == 0, f"Fetch failed: {fetch_result.stderr}"

        # File should not be symlinked yet (just fetched, not merged)
        assert not (main / "fetched_file.txt").exists()

        # Now pull
        pull_result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "pull"],
            cwd=main, capture_output=True, text=True,
        )
        assert pull_result.returncode == 0, f"Pull failed: {pull_result.stderr}"

        # Now file should be symlinked
        assert (main / "fetched_file.txt").is_symlink()
        assert (main / "fetched_file.txt").read_text() == "fetch content"


class TestPullStateConsistency:
    """Test that state.json stays consistent through various pull scenarios."""

    def test_state_symlinks_match_actual_symlinks_after_pull(self, project_with_overlay):
        """All symlinks in state.json correspond to actual symlinks on disk after pull."""
        main, origin, config = project_with_overlay

        # Add several files to origin across multiple commits
        for i in range(5):
            push_to_origin(origin, f"file_{i}.txt", f"content {i}", f"add file {i}")

        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "pull"],
            cwd=main, capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Pull failed: {result.stderr}"

        state = read_state(main)
        for symlink_path in state["symlinks"]:
            full_path = main / symlink_path
            assert full_path.is_symlink(), (
                f"State says {symlink_path} is a symlink but it's not on disk"
            )

    def test_repeated_pulls_dont_duplicate_state(self, project_with_overlay):
        """Repeated pulls don't cause duplicate entries in state."""
        main, origin, config = project_with_overlay

        push_to_origin(origin, "repeated.txt", "content", "add file")

        # Pull multiple times
        for _ in range(3):
            result = subprocess.run(
                [sys.executable, "-m", "repoverlay", "pull"],
                cwd=main, capture_output=True, text=True,
            )
            assert result.returncode == 0

        state = read_state(main)
        # No duplicates in symlinks list
        assert len(state["symlinks"]) == len(set(state["symlinks"]))

    def test_pull_add_delete_cycle_state_consistent(self, project_with_overlay):
        """State stays consistent through add/delete cycles in origin."""
        main, origin, config = project_with_overlay

        # Add a file
        push_to_origin(origin, "temp.txt", "temp", "add temp")

        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "pull"],
            cwd=main, capture_output=True, text=True,
        )
        assert result.returncode == 0

        state = read_state(main)
        assert "temp.txt" in state["symlinks"]
        assert (main / "temp.txt").is_symlink()

        # Delete the file
        delete_in_origin(origin, "temp.txt", "remove temp")

        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "pull"],
            cwd=main, capture_output=True, text=True,
        )
        assert result.returncode == 0

        state = read_state(main)
        assert "temp.txt" not in state["symlinks"]
        assert not (main / "temp.txt").is_symlink()

    def test_unlink_after_pull_removes_all_symlinks(self, project_with_overlay):
        """Unlink after pull removes all symlinks including newly pulled ones."""
        main, origin, config = project_with_overlay

        # Add files via pull
        push_to_origin(origin, "pulled_a.txt", "a", "add a")
        push_to_origin(origin, "pulled_b.txt", "b", "add b")

        subprocess.run(
            [sys.executable, "-m", "repoverlay", "pull"],
            cwd=main, capture_output=True, text=True,
        )

        assert (main / "pulled_a.txt").is_symlink()
        assert (main / "pulled_b.txt").is_symlink()

        # Unlink
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "unlink", "--remove-repo"],
            cwd=main, capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Unlink failed: {result.stderr}"

        # All symlinks gone
        assert not (main / "pulled_a.txt").exists()
        assert not (main / "pulled_b.txt").exists()
        assert not (main / ".env.production").exists()
        assert not (main / "secrets" / "db.yaml").exists()

    def test_multiple_pull_cycles_state_accurate(self, project_with_overlay):
        """State is accurate after multiple add/modify/delete pull cycles."""
        main, origin, config = project_with_overlay

        # Cycle 1: add files
        push_to_origin(origin, "cycle_a.txt", "a1", "add a")
        push_to_origin(origin, "cycle_b.txt", "b1", "add b")
        subprocess.run(
            [sys.executable, "-m", "repoverlay", "pull"],
            cwd=main, capture_output=True, text=True,
        )

        state = read_state(main)
        assert "cycle_a.txt" in state["symlinks"]
        assert "cycle_b.txt" in state["symlinks"]

        # Cycle 2: modify one, add new, delete one
        push_to_origin(origin, "cycle_a.txt", "a2", "modify a")
        push_to_origin(origin, "cycle_c.txt", "c1", "add c")
        delete_in_origin(origin, "cycle_b.txt", "delete b")

        subprocess.run(
            [sys.executable, "-m", "repoverlay", "pull"],
            cwd=main, capture_output=True, text=True,
        )

        state = read_state(main)
        assert "cycle_a.txt" in state["symlinks"]
        assert "cycle_b.txt" not in state["symlinks"]
        assert "cycle_c.txt" in state["symlinks"]

        assert (main / "cycle_a.txt").read_text() == "a2"
        assert not (main / "cycle_b.txt").exists()
        assert (main / "cycle_c.txt").read_text() == "c1"


class TestPullWithMappings:
    """Test pull behavior with explicit mappings in config."""

    def test_pull_with_explicit_mappings_only_maps_specified(self, overlay_origin):
        """Pull with explicit mappings only creates symlinks for mapped files."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            from pathlib import Path
            main = Path(tmp) / "main_mapped"
            main.mkdir()
            subprocess.run(["git", "init"], cwd=main, check=True, capture_output=True)

            config = {
                "version": 1,
                "overlay": {
                    "repo": str(overlay_origin),
                    "mappings": [
                        {"src": "secrets", "dst": "config/secrets"},
                        {"src": ".env.production", "dst": ".env"},
                    ],
                },
            }
            (main / ".repoverlay.yaml").write_text(yaml.dump(config))

            result = subprocess.run(
                [sys.executable, "-m", "repoverlay", "clone"],
                cwd=main, capture_output=True, text=True,
            )
            assert result.returncode == 0

            # Push a new file to origin (not in mappings)
            push_to_origin(overlay_origin, "unmapped.txt", "unmapped", "add unmapped")

            result = subprocess.run(
                [sys.executable, "-m", "repoverlay", "pull"],
                cwd=main, capture_output=True, text=True,
            )
            assert result.returncode == 0

            # Mapped files should be symlinked
            assert (main / ".env").is_symlink()
            assert (main / "config" / "secrets").is_symlink()

            # Unmapped file should NOT be symlinked
            assert not (main / "unmapped.txt").exists()

    def test_pull_modified_mapped_file(self, overlay_origin):
        """Pull updates mapped file content correctly."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            from pathlib import Path
            main = Path(tmp) / "main_mapped2"
            main.mkdir()
            subprocess.run(["git", "init"], cwd=main, check=True, capture_output=True)

            config = {
                "version": 1,
                "overlay": {
                    "repo": str(overlay_origin),
                    "mappings": [
                        {"src": ".env.production", "dst": ".env"},
                    ],
                },
            }
            (main / ".repoverlay.yaml").write_text(yaml.dump(config))

            subprocess.run(
                [sys.executable, "-m", "repoverlay", "clone"],
                cwd=main, capture_output=True, text=True,
            )

            assert (main / ".env").read_text() == "API_KEY=xxx"

            push_to_origin(overlay_origin, ".env.production", "API_KEY=updated", "update env")

            result = subprocess.run(
                [sys.executable, "-m", "repoverlay", "pull"],
                cwd=main, capture_output=True, text=True,
            )
            assert result.returncode == 0

            assert (main / ".env").read_text() == "API_KEY=updated"


class TestCheckoutConsistency:
    """Test checkout followed by sync for branch switching."""

    def test_checkout_branch_updates_symlinks(self, project_with_overlay):
        """Checkout a branch updates symlinks to match branch content."""
        main, origin, config = project_with_overlay

        # Create a branch in origin with different content
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=origin, check=True, capture_output=True,
        )
        push_to_origin(origin, "feature_only.txt", "feature content", "add feature file")
        # Go back to main branch in origin
        subprocess.run(
            ["git", "checkout", "-"],
            cwd=origin, check=True, capture_output=True,
        )

        # Fetch in overlay repo
        subprocess.run(
            [sys.executable, "-m", "repoverlay", "fetch"],
            cwd=main, capture_output=True, text=True,
        )

        # Checkout feature branch
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "checkout", "feature"],
            cwd=main, capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Checkout failed: {result.stderr}"

        # Feature file should be symlinked
        assert (main / "feature_only.txt").is_symlink()
        assert (main / "feature_only.txt").read_text() == "feature content"

        state = read_state(main)
        assert "feature_only.txt" in state["symlinks"]

    def test_checkout_back_to_main_removes_feature_symlinks(self, project_with_overlay):
        """Switching back from feature branch removes feature-only symlinks."""
        main, origin, config = project_with_overlay
        repo_dir = main / ".repoverlay" / "repo"

        # Get the current branch name
        branch_result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=repo_dir, capture_output=True, text=True,
        )
        main_branch = branch_result.stdout.strip()

        # Create a branch in origin with extra file
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=origin, check=True, capture_output=True,
        )
        push_to_origin(origin, "feature_file.txt", "feature", "feature commit")
        subprocess.run(
            ["git", "checkout", main_branch],
            cwd=origin, check=True, capture_output=True,
        )

        # Fetch and checkout feature
        subprocess.run(
            [sys.executable, "-m", "repoverlay", "fetch"],
            cwd=main, capture_output=True, text=True,
        )
        subprocess.run(
            [sys.executable, "-m", "repoverlay", "checkout", "feature"],
            cwd=main, capture_output=True, text=True,
        )
        assert (main / "feature_file.txt").is_symlink()

        # Switch back to main branch
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "checkout", main_branch],
            cwd=main, capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Checkout failed: {result.stderr}"

        # Feature-only file should no longer be symlinked
        assert not (main / "feature_file.txt").is_symlink()

        state = read_state(main)
        assert "feature_file.txt" not in state["symlinks"]
