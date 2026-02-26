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


def checkout(repo_dir: Path, ref: str, *, new_branch: bool = False) -> None:
    """Checkout a specific ref in a repository.

    Args:
        repo_dir: Path to the repository.
        ref: Branch, tag, or commit to checkout.
        new_branch: If True, create a new branch with -b flag.

    Raises:
        GitError: If checkout fails.
    """
    cmd = ["git", "checkout"]
    if new_branch:
        cmd.append("-b")
    cmd.append(ref)
    result = subprocess.run(
        cmd,
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


def has_upstream(repo_dir: Path) -> bool:
    """Check if the current branch has an upstream tracking branch.

    Args:
        repo_dir: Path to the repository.

    Returns:
        True if upstream is configured.
    """
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "@{u}"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def push(repo_dir: Path) -> None:
    """Push to remote. Automatically sets upstream if not configured.

    Args:
        repo_dir: Path to the repository.

    Raises:
        GitError: If push fails.
    """
    if not has_upstream(repo_dir):
        branch = get_current_branch(repo_dir)
        if branch:
            run_git(repo_dir, ["push", "--set-upstream", "origin", branch], capture=True)
            return
    run_git(repo_dir, ["push"], capture=True)


def status(
    repo_dir: Path,
    root_dir: Path | None = None,
    extra_unstaged: list[str] | None = None,
) -> subprocess.CompletedProcess:
    """Show git status with encrypted files integrated.

    Args:
        repo_dir: Path to the repository.
        root_dir: Project root for path transformation (if None, no transformation)
        extra_unstaged: Additional files to show as unstaged (e.g., decrypted files)

    Returns:
        CompletedProcess result
    """
    import os
    import sys

    cwd = Path.cwd()

    def to_display_path(overlay_path: str) -> str:
        """Convert overlay-relative path to display path (relative to cwd).

        The overlay path is the logical path in the overlay (e.g., ansible/jenkins/...).
        The display path is relative to the user's current working directory.
        """
        if root_dir is None:
            return overlay_path
        # The symlink would be at root_dir / overlay_path
        symlink_location = root_dir / overlay_path
        try:
            return os.path.relpath(symlink_location, cwd)
        except ValueError:
            return overlay_path

    # Capture git status output so we can modify it
    result = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
    )

    # Parse porcelain output - paths are already repo-relative from git
    # Format: XY PATH where X=index status, Y=worktree status, then space, then path
    # IMPORTANT: Don't strip() as leading space is the index status for unchanged files
    staged_files = []
    unstaged_files = []
    untracked_files = []

    for line in result.stdout.split("\n"):
        if not line or len(line) < 4:
            continue
        index_status = line[0]
        worktree_status = line[1]
        filename = line[3:]  # Skip XY and space, get path
        display_path = to_display_path(filename)

        if index_status == "?":
            untracked_files.append(display_path)
        else:
            if index_status != " ":
                staged_files.append((index_status, display_path))
            if worktree_status != " ":
                unstaged_files.append((worktree_status, display_path))

    # Add extra unstaged files (decoded files from encrypted sources)
    # extra_unstaged contains the decoded path (e.g., "ansible/jenkins/...")
    if extra_unstaged:
        for extra_file in extra_unstaged:
            # extra_file is already the overlay-relative path (decoded filename without .enc)
            display_path = to_display_path(extra_file)
            unstaged_files.append(("M", display_path))

    # Get branch info
    branch_result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
    )
    branch = branch_result.stdout.strip() if branch_result.returncode == 0 else None

    # Get tracking info
    tracking_info = ""
    if branch:
        tracking_result = subprocess.run(
            ["git", "status", "--porcelain=v2", "--branch"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        for line in tracking_result.stdout.split("\n"):
            if line.startswith("# branch.upstream"):
                upstream = line.split()[-1] if len(line.split()) > 1 else ""
                tracking_info = f"Your branch is up to date with '{upstream}'."
            elif line.startswith("# branch.ab"):
                parts = line.split()
                ahead = int(parts[2][1:]) if len(parts) > 2 else 0
                behind = int(parts[3][1:]) if len(parts) > 3 else 0
                if ahead > 0 and behind > 0:
                    tracking_info = f"Your branch and 'origin/{branch}' have diverged."
                elif ahead > 0:
                    tracking_info = f"Your branch is ahead of 'origin/{branch}' by {ahead} commit(s)."
                elif behind > 0:
                    tracking_info = f"Your branch is behind 'origin/{branch}' by {behind} commit(s)."

    # Print formatted output
    if branch:
        print(f"On branch {branch}")
    if tracking_info:
        print(tracking_info)
    print()

    if staged_files:
        print("Changes to be committed:")
        print('  (use "git restore --staged <file>..." to unstage)')
        for status_char, filepath in staged_files:
            status_word = _status_char_to_word(status_char)
            print(f"\t\x1b[32m{status_word}:   {filepath}\x1b[m")
        print()

    if unstaged_files:
        print("Changes not staged for commit:")
        print('  (use "git add <file>..." to update what will be committed)')
        print('  (use "git restore <file>..." to discard changes in working directory)')
        print('  (use "repoverlay commit" to re-encrypt and commit decrypted files)')
        print()
        for status_char, filepath in unstaged_files:
            status_word = _status_char_to_word(status_char)
            print(f"\t\x1b[31m{status_word}:   {filepath}\x1b[m")
        print()

    if untracked_files:
        print("Untracked files:")
        print('  (use "git add <file>..." to include in what will be committed)')
        for filepath in untracked_files:
            print(f"\t\x1b[31m{filepath}\x1b[m")
        print()

    if not staged_files and not unstaged_files and not untracked_files:
        print("nothing to commit, working tree clean")

    return subprocess.CompletedProcess(
        args=["git", "status"],
        returncode=result.returncode,
    )


def _status_char_to_word(char: str) -> str:
    """Convert git status character to word."""
    mapping = {
        "M": "modified",
        "A": "new file",
        "D": "deleted",
        "R": "renamed",
        "C": "copied",
        "U": "updated",
        "?": "untracked",
    }
    return mapping.get(char, "modified")


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


def log(repo_dir: Path, args: list[str] | None = None) -> subprocess.CompletedProcess:
    """Show git log.

    Args:
        repo_dir: Path to the repository.
        args: Additional arguments

    Returns:
        CompletedProcess result
    """
    cmd = ["log"]
    if args:
        cmd.extend(args)
    return run_git(repo_dir, cmd, capture=False)


def rm(repo_dir: Path, files: list[str], *, cached: bool = False) -> None:
    """Remove files from the repository.

    Args:
        repo_dir: Path to the repository.
        files: Files to remove
        cached: If True, only remove from the index (keep working copy)

    Raises:
        GitError: If rm fails.
    """
    cmd = ["rm"]
    if cached:
        cmd.append("--cached")
    cmd.extend(files)
    run_git(repo_dir, cmd, capture=True)


def add(repo_dir: Path, files: list[str]) -> None:
    """Add files to staging.

    Args:
        repo_dir: Path to the repository.
        files: Files to add

    Raises:
        GitError: If add fails.
    """
    run_git(repo_dir, ["add"] + files, capture=True)


def restore(repo_dir: Path, files: list[str], *, staged: bool = False) -> None:
    """Restore files (git restore).

    Args:
        repo_dir: Path to the repository.
        files: Files to restore
        staged: If True, restore staged changes (--staged)

    Raises:
        GitError: If restore fails.
    """
    if staged and not has_commits(repo_dir):
        # No HEAD yet — use git rm --cached to unstage
        run_git(repo_dir, ["rm", "-r", "--cached"] + files, capture=True)
        return

    cmd = ["restore"]
    if staged:
        cmd.append("--staged")
    cmd.extend(files)
    run_git(repo_dir, cmd, capture=True)


def has_commits(repo_dir: Path) -> bool:
    """Check if a repository has any commits.

    Args:
        repo_dir: Path to the repository.

    Returns:
        True if the repository has at least one commit.
    """
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def reset(repo_dir: Path, files: list[str] | None = None) -> None:
    """Unstage files (git reset HEAD, or git rm --cached on empty repos).

    Args:
        repo_dir: Path to the repository.
        files: Files to unstage (if None, unstages all)

    Raises:
        GitError: If reset fails.
    """
    if not has_commits(repo_dir):
        # No HEAD yet — use git rm --cached to unstage
        if files:
            run_git(repo_dir, ["rm", "--cached"] + files, capture=True)
        else:
            run_git(repo_dir, ["rm", "-r", "--cached", "."], capture=True)
        return

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


def get_tracked_files(repo_dir: Path, paths: list[str]) -> list[str]:
    """Check which of the given paths are tracked by git.

    Args:
        repo_dir: Path to the repository.
        paths: List of paths to check (relative to repo_dir).

    Returns:
        List of paths that are tracked (in the index).
    """
    if not paths:
        return []

    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--"] + paths,
        cwd=repo_dir,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        # Some or all files are not tracked; fall back to checking one-by-one
        # by listing all tracked files and intersecting
        result = subprocess.run(
            ["git", "ls-files", "--"] + paths,
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return []

    tracked = result.stdout.strip()
    if not tracked:
        return []
    return tracked.split("\n")
