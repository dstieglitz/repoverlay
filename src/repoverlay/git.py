"""Git command wrapper."""

import subprocess
from pathlib import Path


class GitError(Exception):
    """Raised when git command fails."""
    pass


def clone(repo_url: str, target_dir: Path) -> None:
    """Clone a git repository.

    Args:
        repo_url: URL or path to the repository.
        target_dir: Directory to clone into.

    Raises:
        GitError: If clone fails.
    """
    result = subprocess.run(
        ["git", "clone", repo_url, str(target_dir)],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise GitError(f"Clone failed: {result.stderr.strip()}")


def checkout(repo_dir: Path, ref: str) -> None:
    """Checkout a specific ref in a repository.

    Args:
        repo_dir: Path to the repository.
        ref: Branch, tag, or commit to checkout.

    Raises:
        GitError: If checkout fails.
    """
    result = subprocess.run(
        ["git", "checkout", ref],
        cwd=repo_dir,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise GitError(f"Checkout failed: {result.stderr.strip()}")


def get_remote_url(repo_dir: Path, remote: str = "origin") -> str:
    """Get the URL of a remote.

    Args:
        repo_dir: Path to the repository.
        remote: Name of the remote (default: origin)

    Returns:
        Remote URL

    Raises:
        GitError: If command fails.
    """
    result = subprocess.run(
        ["git", "remote", "get-url", remote],
        cwd=repo_dir,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise GitError(f"Failed to get remote URL: {result.stderr.strip()}")

    return result.stdout.strip()


def run_git(repo_dir: Path, args: list[str], capture: bool = False) -> subprocess.CompletedProcess:
    """Run a git command in a repository.

    Args:
        repo_dir: Path to the repository.
        args: Git command arguments (without 'git' prefix)
        capture: Whether to capture output (default: stream to terminal)

    Returns:
        CompletedProcess result

    Raises:
        GitError: If command fails and capture is True
    """
    cmd = ["git"] + args

    if capture:
        result = subprocess.run(
            cmd,
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise GitError(result.stderr.strip() or f"Git command failed: {' '.join(args)}")
        return result
    else:
        # Stream output to terminal
        result = subprocess.run(cmd, cwd=repo_dir)
        return result


def fetch(repo_dir: Path) -> None:
    """Fetch from remote.

    Args:
        repo_dir: Path to the repository.

    Raises:
        GitError: If fetch fails.
    """
    run_git(repo_dir, ["fetch"], capture=True)


def pull(repo_dir: Path) -> None:
    """Pull from remote.

    Args:
        repo_dir: Path to the repository.

    Raises:
        GitError: If pull fails.
    """
    run_git(repo_dir, ["pull"], capture=True)


def push(repo_dir: Path) -> None:
    """Push to remote.

    Args:
        repo_dir: Path to the repository.

    Raises:
        GitError: If push fails.
    """
    run_git(repo_dir, ["push"], capture=True)


def status(repo_dir: Path) -> subprocess.CompletedProcess:
    """Show git status.

    Args:
        repo_dir: Path to the repository.

    Returns:
        CompletedProcess result
    """
    return run_git(repo_dir, ["status"], capture=False)


def diff(repo_dir: Path, args: list[str] | None = None) -> subprocess.CompletedProcess:
    """Show git diff.

    Args:
        repo_dir: Path to the repository.
        args: Additional arguments

    Returns:
        CompletedProcess result
    """
    cmd = ["diff"]
    if args:
        cmd.extend(args)
    return run_git(repo_dir, cmd, capture=False)


def add(repo_dir: Path, files: list[str]) -> None:
    """Add files to staging.

    Args:
        repo_dir: Path to the repository.
        files: Files to add

    Raises:
        GitError: If add fails.
    """
    run_git(repo_dir, ["add"] + files, capture=True)


def commit(repo_dir: Path, message: str | None = None, args: list[str] | None = None) -> None:
    """Create a commit.

    Args:
        repo_dir: Path to the repository.
        message: Commit message (optional if using -m in args)
        args: Additional arguments

    Raises:
        GitError: If commit fails.
    """
    cmd = ["commit"]
    if message:
        cmd.extend(["-m", message])
    if args:
        cmd.extend(args)
    run_git(repo_dir, cmd, capture=True)


def merge(repo_dir: Path, branch: str | None = None) -> None:
    """Merge a branch.

    Args:
        repo_dir: Path to the repository.
        branch: Branch to merge (optional)

    Raises:
        GitError: If merge fails.
    """
    cmd = ["merge"]
    if branch:
        cmd.append(branch)
    run_git(repo_dir, cmd, capture=True)
