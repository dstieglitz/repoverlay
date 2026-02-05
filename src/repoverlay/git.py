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


def pull(repo_dir: Path, opts: list[str] | None = None) -> None:
    """Pull from remote.

    Args:
        repo_dir: Path to the repository.
        opts: Additional options (e.g., ["--rebase"], ["--no-rebase"], ["--ff-only"])

    Raises:
        GitError: If pull fails.
    """
    cmd = ["pull"]
    if opts:
        cmd.extend(opts)
    run_git(repo_dir, cmd, capture=True)


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


def reset(repo_dir: Path, files: list[str] | None = None) -> None:
    """Unstage files (git reset HEAD).

    Args:
        repo_dir: Path to the repository.
        files: Files to unstage (if None, unstages all)

    Raises:
        GitError: If reset fails.
    """
    cmd = ["reset", "HEAD"]
    if files:
        cmd.extend(files)
    run_git(repo_dir, cmd, capture=True)


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


def is_bare_repo(repo_dir: Path) -> bool:
    """Check if a repository is bare.

    Args:
        repo_dir: Path to the repository.

    Returns:
        True if the repository is bare, False otherwise.
    """
    result = subprocess.run(
        ["git", "rev-parse", "--is-bare-repository"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def get_current_branch(repo_dir: Path) -> str | None:
    """Get the currently checked out branch.

    Args:
        repo_dir: Path to the repository.

    Returns:
        Branch name, or None if in detached HEAD state or not a git repo.
    """
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    branch = result.stdout.strip()
    return branch if branch else None


def pull_from(repo_dir: Path, source_repo: Path, branch: str) -> None:
    """Pull changes from a source repository into this repository.

    This is used to sync changes from an overlay repo into a local non-bare origin.

    Args:
        repo_dir: Path to the repository to pull into.
        source_repo: Path to the source repository to pull from.
        branch: Branch to pull.

    Raises:
        GitError: If pull fails.
    """
    result = subprocess.run(
        ["git", "pull", str(source_repo), branch],
        cwd=repo_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise GitError(f"Pull failed: {result.stderr.strip()}")


def has_uncommitted_changes(repo_dir: Path) -> tuple[bool, list[str]]:
    """Check if there are uncommitted changes (staged or unstaged).

    Args:
        repo_dir: Path to the repository.

    Returns:
        Tuple of (has_changes, list of changed files)
    """
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return False, []

    output = result.stdout.strip()
    if not output:
        return False, []

    # Parse the porcelain output to get file list
    changed_files = []
    for line in output.split("\n"):
        if line:
            # Format is "XY filename" where XY is the status
            changed_files.append(line)
    return True, changed_files


def has_unpushed_commits(repo_dir: Path) -> tuple[bool, int]:
    """Check if there are commits not pushed to remote.

    Args:
        repo_dir: Path to the repository.

    Returns:
        Tuple of (has_unpushed, count of unpushed commits)
    """
    # First check if there's an upstream configured
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "@{u}"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        # No upstream configured, try to use origin/<branch>
        branch = get_current_branch(repo_dir)
        if not branch:
            return False, 0

        # Check if origin/<branch> exists
        result = subprocess.run(
            ["git", "rev-parse", "--verify", f"origin/{branch}"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            # No remote tracking branch, can't determine
            return False, 0

        upstream = f"origin/{branch}"
    else:
        upstream = result.stdout.strip()

    # Count commits ahead of upstream
    result = subprocess.run(
        ["git", "rev-list", "--count", f"{upstream}..HEAD"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        return False, 0

    count = int(result.stdout.strip())
    return count > 0, count
