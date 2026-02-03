"""Tests for git module."""

import subprocess

import pytest

from repoverlay import git


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary git repository."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    return repo


@pytest.fixture
def git_repo_with_commit(git_repo):
    """Create a git repo with an initial commit."""
    (git_repo / "file.txt").write_text("content")
    subprocess.run(["git", "add", "."], cwd=git_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=git_repo,
        check=True,
        capture_output=True,
    )
    return git_repo


@pytest.fixture
def git_repo_with_remote(tmp_path):
    """Create a git repo with a remote."""
    # Create "remote" repo
    remote = tmp_path / "remote"
    remote.mkdir()
    subprocess.run(["git", "init", "--bare"], cwd=remote, check=True, capture_output=True)

    # Create local repo
    local = tmp_path / "local"
    subprocess.run(
        ["git", "clone", str(remote), str(local)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=local,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=local,
        check=True,
        capture_output=True,
    )

    # Add initial commit
    (local / "file.txt").write_text("content")
    subprocess.run(["git", "add", "."], cwd=local, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=local,
        check=True,
        capture_output=True,
    )

    # Get current branch name (could be master or main)
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=local,
        capture_output=True,
        text=True,
    )
    branch = result.stdout.strip() or "master"

    subprocess.run(
        ["git", "push", "-u", "origin", branch],
        cwd=local,
        check=True,
        capture_output=True,
    )

    return local, remote


class TestClone:
    """Tests for git.clone function."""

    def test_clone_success(self, tmp_path, git_repo_with_commit):
        """Clone succeeds with valid repo."""
        target = tmp_path / "clone"
        git.clone(str(git_repo_with_commit), target)

        assert target.exists()
        assert (target / ".git").is_dir()
        assert (target / "file.txt").read_text() == "content"

    def test_clone_invalid_url(self, tmp_path):
        """Clone fails with invalid URL."""
        target = tmp_path / "clone"

        with pytest.raises(git.GitError, match="Clone failed"):
            git.clone("invalid://not-a-repo", target)


class TestCheckout:
    """Tests for git.checkout function."""

    def test_checkout_branch(self, git_repo_with_commit):
        """Checkout existing branch succeeds."""
        # Create a branch
        subprocess.run(
            ["git", "branch", "feature"],
            cwd=git_repo_with_commit,
            check=True,
            capture_output=True,
        )

        git.checkout(git_repo_with_commit, "feature")

        # Verify we're on the branch
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=git_repo_with_commit,
            capture_output=True,
            text=True,
        )
        assert result.stdout.strip() == "feature"

    def test_checkout_invalid_ref(self, git_repo_with_commit):
        """Checkout invalid ref fails."""
        with pytest.raises(git.GitError, match="Checkout failed"):
            git.checkout(git_repo_with_commit, "nonexistent-branch")


class TestGetRemoteUrl:
    """Tests for git.get_remote_url function."""

    def test_get_remote_url(self, git_repo_with_remote):
        """Gets remote URL correctly."""
        local, remote = git_repo_with_remote

        url = git.get_remote_url(local)
        assert str(remote) in url

    def test_get_remote_url_no_remote(self, git_repo_with_commit):
        """Fails when no remote exists."""
        with pytest.raises(git.GitError, match="Failed to get remote URL"):
            git.get_remote_url(git_repo_with_commit)


class TestRunGit:
    """Tests for git.run_git function."""

    def test_run_git_capture(self, git_repo_with_commit):
        """Run git with capture returns output."""
        result = git.run_git(git_repo_with_commit, ["log", "--oneline"], capture=True)

        assert result.returncode == 0
        assert "initial" in result.stdout

    def test_run_git_no_capture(self, git_repo_with_commit):
        """Run git without capture streams to terminal."""
        result = git.run_git(git_repo_with_commit, ["status"], capture=False)

        assert result.returncode == 0

    def test_run_git_error_with_capture(self, git_repo):
        """Run git error raises GitError when capturing."""
        with pytest.raises(git.GitError):
            git.run_git(git_repo, ["log"], capture=True)  # No commits yet


class TestStatus:
    """Tests for git.status function."""

    def test_status(self, git_repo_with_commit):
        """Status returns result."""
        result = git.status(git_repo_with_commit)
        assert result.returncode == 0


class TestDiff:
    """Tests for git.diff function."""

    def test_diff(self, git_repo_with_commit):
        """Diff returns result."""
        result = git.diff(git_repo_with_commit)
        assert result.returncode == 0

    def test_diff_with_args(self, git_repo_with_commit):
        """Diff with args works."""
        result = git.diff(git_repo_with_commit, ["--stat"])
        assert result.returncode == 0


class TestAdd:
    """Tests for git.add function."""

    def test_add_file(self, git_repo_with_commit):
        """Add stages file."""
        (git_repo_with_commit / "new.txt").write_text("new")

        git.add(git_repo_with_commit, ["new.txt"])

        # Verify file is staged
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=git_repo_with_commit,
            capture_output=True,
            text=True,
        )
        assert "new.txt" in result.stdout

    def test_add_nonexistent_file(self, git_repo_with_commit):
        """Add nonexistent file fails."""
        with pytest.raises(git.GitError):
            git.add(git_repo_with_commit, ["nonexistent.txt"])


class TestCommit:
    """Tests for git.commit function."""

    def test_commit_with_message(self, git_repo_with_commit):
        """Commit with message succeeds."""
        (git_repo_with_commit / "new.txt").write_text("new")
        subprocess.run(
            ["git", "add", "new.txt"],
            cwd=git_repo_with_commit,
            check=True,
            capture_output=True,
        )

        git.commit(git_repo_with_commit, message="add new file")

        # Verify commit
        result = subprocess.run(
            ["git", "log", "-1", "--format=%s"],
            cwd=git_repo_with_commit,
            capture_output=True,
            text=True,
        )
        assert "add new file" in result.stdout

    def test_commit_nothing_staged(self, git_repo_with_commit):
        """Commit fails when nothing staged."""
        with pytest.raises(git.GitError):
            git.commit(git_repo_with_commit, message="empty")


class TestFetch:
    """Tests for git.fetch function."""

    def test_fetch(self, git_repo_with_remote):
        """Fetch succeeds."""
        local, _ = git_repo_with_remote
        git.fetch(local)  # Should not raise


class TestPull:
    """Tests for git.pull function."""

    def test_pull(self, git_repo_with_remote):
        """Pull succeeds."""
        local, _ = git_repo_with_remote
        git.pull(local)  # Should not raise


class TestPush:
    """Tests for git.push function."""

    def test_push(self, git_repo_with_remote):
        """Push succeeds."""
        local, _ = git_repo_with_remote

        # Make a change
        (local / "new.txt").write_text("new")
        subprocess.run(["git", "add", "."], cwd=local, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "new"],
            cwd=local,
            check=True,
            capture_output=True,
        )

        git.push(local)  # Should not raise


class TestMerge:
    """Tests for git.merge function."""

    def test_merge(self, git_repo_with_commit):
        """Merge succeeds."""
        # Create and checkout feature branch
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=git_repo_with_commit,
            check=True,
            capture_output=True,
        )
        (git_repo_with_commit / "feature.txt").write_text("feature")
        subprocess.run(
            ["git", "add", "."],
            cwd=git_repo_with_commit,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "feature"],
            cwd=git_repo_with_commit,
            check=True,
            capture_output=True,
        )

        # Go back to master/main and merge
        subprocess.run(
            ["git", "checkout", "master"],
            cwd=git_repo_with_commit,
            capture_output=True,
        )
        # If master doesn't exist, try main
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=git_repo_with_commit,
            capture_output=True,
            text=True,
        )
        if not result.stdout.strip():
            subprocess.run(
                ["git", "checkout", "main"],
                cwd=git_repo_with_commit,
                capture_output=True,
            )

        git.merge(git_repo_with_commit, "feature")

        # Verify merge
        assert (git_repo_with_commit / "feature.txt").exists()
