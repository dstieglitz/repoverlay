"""Command-line interface."""

import argparse
import sys

from . import __version__, git, sops
from .config import ConfigError, find_config, load_config
from .ignore import matches_any_pattern
from .output import Output, set_output
from .intellij import configure_vcs_root, remove_vcs_root
from .overlay import (
    OverlayError,
    UncommittedChangesError,
    UnpushedCommitsError,
    clone_overlay,
    get_decoded_dir,
    get_repo_dir,
    sync_overlay,
    unlink_overlay,
)
from .state import read_state, write_state


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, 1 for error, 2 for partial success).
    """
    parser = argparse.ArgumentParser(
        prog="repoverlay",
        description="Clone overlay repos and create symlinks",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    # Global flags
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress informational output",
    )

    subparsers = parser.add_subparsers(dest="command")

    # clone command
    clone_parser = subparsers.add_parser("clone", help="Clone overlay repo and create symlinks")
    clone_parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Overwrite existing .repoverlay/repo/",
    )
    clone_parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview changes without executing",
    )
    clone_parser.add_argument(
        "--intellij",
        action="store_true",
        help="Configure IntelliJ IDEA to track overlay repo as VCS root",
    )

    # sync command
    sync_parser = subparsers.add_parser("sync", help="Sync symlinks with current config")
    sync_parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Overwrite existing destinations",
    )
    sync_parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview changes without executing",
    )
    sync_parser.add_argument(
        "--intellij",
        action="store_true",
        help="Configure IntelliJ IDEA to track overlay repo as VCS root",
    )

    # unlink command
    unlink_parser = subparsers.add_parser("unlink", help="Remove all symlinks and clean up")
    unlink_parser.add_argument(
        "--remove-repo",
        action="store_true",
        help="Also remove .repoverlay/ directory",
    )
    unlink_parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Proceed even with uncommitted changes",
    )
    unlink_parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview changes without executing",
    )

    # Git passthrough commands
    subparsers.add_parser("status", help="Show git status of overlay repo")
    subparsers.add_parser("fetch", help="Fetch updates from overlay remote")

    pull_parser = subparsers.add_parser("pull", help="Pull updates and sync symlinks")
    pull_parser.add_argument("--rebase", action="store_true", help="Rebase local commits on top of remote")
    pull_parser.add_argument("--merge", action="store_true", help="Merge remote changes (create merge commit)")
    pull_parser.add_argument("--ff-only", action="store_true", help="Only fast-forward, fail if not possible")

    subparsers.add_parser("push", help="Push overlay repo changes")

    commit_parser = subparsers.add_parser("commit", help="Commit changes in overlay repo")
    commit_parser.add_argument("-a", "--all", action="store_true", help="Automatically stage modified/deleted files")
    commit_parser.add_argument("-m", "--message", help="Commit message")
    commit_parser.add_argument("args", nargs="*", help="Additional git commit arguments")

    add_parser = subparsers.add_parser("add", help="Add files to overlay repo staging")
    add_parser.add_argument("files", nargs="+", help="Files to add")
    add_parser.add_argument(
        "--encrypt", "-e",
        action="store_true",
        help="Encrypt files with SOPS before adding (creates .enc files)",
    )

    reset_parser = subparsers.add_parser("reset", help="Unstage files from overlay repo")
    reset_parser.add_argument("files", nargs="*", help="Files to unstage (default: all staged files)")

    diff_parser = subparsers.add_parser("diff", help="Show diff in overlay repo")
    diff_parser.add_argument("args", nargs=argparse.REMAINDER, help="Additional git diff arguments")

    checkout_parser = subparsers.add_parser("checkout", help="Checkout ref in overlay repo and sync")
    checkout_parser.add_argument("ref", help="Branch, tag, or commit to checkout")

    merge_parser = subparsers.add_parser("merge", help="Merge branch in overlay repo and sync")
    merge_parser.add_argument("branch", nargs="?", help="Branch to merge")

    # list command
    subparsers.add_parser("list", help="List files in overlay repo")

    args = parser.parse_args()

    # Set up output handler
    output = Output(no_color=args.no_color, quiet=args.quiet)
    set_output(output)

    if args.command is None:
        parser.print_help()
        return 0

    # Route to command handler
    handlers = {
        "clone": lambda: cmd_clone(args, output),
        "sync": lambda: cmd_sync(args, output),
        "unlink": lambda: cmd_unlink(args, output),
        "status": lambda: cmd_status(output),
        "fetch": lambda: cmd_fetch(output),
        "pull": lambda: cmd_pull(args, output),
        "push": lambda: cmd_push(output),
        "commit": lambda: cmd_commit(args, output),
        "add": lambda: cmd_add(args, output),
        "reset": lambda: cmd_reset(args, output),
        "diff": lambda: cmd_diff(args, output),
        "checkout": lambda: cmd_checkout(args, output),
        "merge": lambda: cmd_merge(args, output),
        "list": lambda: cmd_list(output),
    }

    handler = handlers.get(args.command)
    if handler:
        return handler()

    return 0


def _get_config_and_root(output: Output) -> tuple:
    """Find config and load it.

    Args:
        output: Output handler

    Returns:
        Tuple of (config, root_dir) or None on error
    """
    try:
        config_path = find_config()
    except ConfigError as e:
        output.error(str(e))
        return None

    try:
        config = load_config(config_path)
    except ConfigError as e:
        output.error(str(e))
        return None

    return config, config_path.parent


def _get_repo_dir_or_error(output: Output):
    """Get the repo directory, erroring if not cloned.

    Args:
        output: Output handler

    Returns:
        repo_dir Path or None on error
    """
    try:
        config_path = find_config()
    except ConfigError as e:
        output.error(str(e))
        return None

    root_dir = config_path.parent
    repo_dir = get_repo_dir(root_dir)

    if not repo_dir.exists():
        output.error("Overlay repo not cloned. Run 'repoverlay clone' first")
        return None

    return repo_dir, root_dir


def cmd_clone(args, output: Output) -> int:
    """Execute the clone command."""
    result = _get_config_and_root(output)
    if result is None:
        return 1
    config, root_dir = result

    try:
        clone_overlay(
            root_dir,
            config,
            force=args.force,
            dry_run=args.dry_run,
            output=output,
        )
    except OverlayError as e:
        output.error(str(e))
        return 1

    # Configure IntelliJ if requested
    if args.intellij:
        configure_vcs_root(root_dir, dry_run=args.dry_run, output=output)

    return 0


def cmd_sync(args, output: Output) -> int:
    """Execute the sync command."""
    result = _get_config_and_root(output)
    if result is None:
        return 1
    config, root_dir = result

    try:
        exit_code = sync_overlay(
            root_dir,
            config,
            force=args.force,
            dry_run=args.dry_run,
            output=output,
        )
    except OverlayError as e:
        output.error(str(e))
        return 1

    # Configure IntelliJ if requested
    if args.intellij:
        configure_vcs_root(root_dir, dry_run=args.dry_run, output=output)

    return exit_code


def cmd_unlink(args, output: Output) -> int:
    """Execute the unlink command."""
    try:
        config_path = find_config()
    except ConfigError as e:
        output.error(str(e))
        return 1

    root_dir = config_path.parent
    remove_repo = args.remove_repo
    force = args.force
    repo_dir = get_repo_dir(root_dir)

    # Pre-check for uncommitted/unpushed changes before any prompts
    if not args.dry_run and repo_dir.exists() and (repo_dir / ".git").exists():
        # Check for unpushed commits first - hard block
        has_unpushed, commit_count = git.has_unpushed_commits(repo_dir)
        if has_unpushed:
            output.error(
                f"Cannot unlink - there are {commit_count} unpushed commit(s) in the overlay repo.\n"
                "Run 'repoverlay push' first, or remove the commits with 'git reset'."
            )
            return 1

        # Check for uncommitted changes - prompt before other questions
        if not force:
            has_uncommitted, changed_files = git.has_uncommitted_changes(repo_dir)
            if has_uncommitted:
                output.warning("Uncommitted changes detected in overlay repo:")
                for changed_file in changed_files:
                    output.info(f"  {changed_file}")
                if sys.stdin.isatty():
                    try:
                        response = input("Continue anyway? [y/N] ").strip().lower()
                        if response in ("y", "yes"):
                            force = True
                        else:
                            output.info("Use --force to proceed with uncommitted changes.")
                            return 1
                    except (EOFError, KeyboardInterrupt):
                        print()  # Newline after ^C
                        return 1
                else:
                    output.info("Use --force to proceed with uncommitted changes.")
                    return 1

    # If not using --remove-repo and not dry-run, prompt the user
    if not remove_repo and not args.dry_run:
        overlay_dir = root_dir / ".repoverlay"
        if overlay_dir.exists() and sys.stdin.isatty():
            try:
                response = input("Remove .repoverlay/ directory? [y/N] ").strip().lower()
                remove_repo = response in ("y", "yes")
            except (EOFError, KeyboardInterrupt):
                print()  # Newline after ^C
                return 1

    try:
        unlink_overlay(
            root_dir,
            remove_repo=remove_repo,
            force=force,
            dry_run=args.dry_run,
            output=output,
        )
        # Clean up IntelliJ VCS root if removing repo
        if remove_repo:
            remove_vcs_root(root_dir, dry_run=args.dry_run, output=output)
    except UnpushedCommitsError as e:
        output.error(str(e))
        return 1
    except UncommittedChangesError as e:
        # This shouldn't happen since we check above, but handle it anyway
        output.warning("Uncommitted changes detected in overlay repo:")
        for changed_file in e.changed_files:
            output.info(f"  {changed_file}")
        output.info("Use --force to proceed with uncommitted changes.")
        return 1
    except OverlayError as e:
        output.error(str(e))
        return 1

    return 0


def cmd_status(output: Output) -> int:
    """Execute git status in overlay repo."""
    result = _get_repo_dir_or_error(output)
    if result is None:
        return 1
    repo_dir, _ = result

    return git.status(repo_dir).returncode


def cmd_list(output: Output) -> int:
    """List files in overlay repo."""
    result = _get_repo_dir_or_error(output)
    if result is None:
        return 1
    repo_dir, _ = result

    # Collect all files, excluding .git directory
    files = []
    for path in repo_dir.rglob("*"):
        if path.is_file():
            try:
                rel_path = path.relative_to(repo_dir)
                # Skip .git directory
                if rel_path.parts[0] == ".git":
                    continue
                files.append(rel_path)
            except ValueError:
                pass

    # Sort files for consistent output
    files.sort()

    # Print each file, marking encrypted ones with color
    for rel_path in files:
        if sops.is_encrypted_file(rel_path):
            # Yellow for encrypted files
            encrypted_text = output._colorize(f"{rel_path} (encrypted)", output.YELLOW)
            print(encrypted_text)
        else:
            print(str(rel_path))

    return 0


def cmd_fetch(output: Output) -> int:
    """Execute git fetch in overlay repo."""
    result = _get_repo_dir_or_error(output)
    if result is None:
        return 1
    repo_dir, _ = result

    try:
        git.fetch(repo_dir)
        output.success("Fetch complete.")
        return 0
    except git.GitError as e:
        output.error(str(e))
        return 1


def cmd_pull(args, output: Output) -> int:
    """Execute git pull in overlay repo, then sync."""
    result = _get_repo_dir_or_error(output)
    if result is None:
        return 1
    repo_dir, root_dir = result

    # Build pull options
    pull_opts = []
    if args.rebase:
        pull_opts.append("--rebase")
    elif args.merge:
        pull_opts.append("--no-rebase")
    elif args.ff_only:
        pull_opts.append("--ff-only")

    try:
        git.pull(repo_dir, pull_opts if pull_opts else None)
        output.success("Pull complete.")
    except git.GitError as e:
        error_msg = str(e)
        # Detect divergent branches error and provide helpful hint
        if "divergent branches" in error_msg or "Need to specify how to reconcile" in error_msg:
            output.error("Divergent branches detected.")
            output.info("")
            output.info("You have local commits that the remote doesn't have, and vice versa.")
            output.info("Choose how to reconcile:")
            output.info("  repoverlay pull --rebase   # Rebase your commits on top of remote")
            output.info("  repoverlay pull --merge    # Create a merge commit")
            output.info("  repoverlay pull --ff-only  # Fail if fast-forward not possible")
            return 1
        output.error(str(e))
        return 1

    # Sync after pull
    cfg_result = _get_config_and_root(output)
    if cfg_result is None:
        return 1
    config, _ = cfg_result

    try:
        return sync_overlay(root_dir, config, output=output)
    except OverlayError as e:
        output.error(str(e))
        return 1


def _is_local_path(repo: str) -> bool:
    """Check if repo is a local path rather than a git URL."""
    if "://" in repo or (repo.startswith("git@") and ":" in repo):
        return False
    return True


def cmd_push(output: Output) -> int:
    """Execute git push in overlay repo."""
    result = _get_repo_dir_or_error(output)
    if result is None:
        return 1
    repo_dir, root_dir = result

    # Get the remote URL to check if it's a local non-bare repo
    try:
        remote_url = git.get_remote_url(repo_dir)
    except git.GitError:
        # No remote configured, just try pushing
        try:
            git.push(repo_dir)
            output.success("Push complete.")
            return 0
        except git.GitError as e:
            output.error(str(e))
            return 1

    # Check if remote is a local path
    if _is_local_path(remote_url):
        from pathlib import Path
        remote_path = Path(remote_url)
        if not remote_path.is_absolute():
            remote_path = (repo_dir / remote_url).resolve()

        if remote_path.exists() and remote_path.is_dir():
            # Check if it's a non-bare repo
            if not git.is_bare_repo(remote_path):
                # Get the branch we're trying to push
                local_branch = git.get_current_branch(repo_dir)
                remote_branch = git.get_current_branch(remote_path)

                if local_branch and remote_branch and local_branch == remote_branch:
                    # The remote has the same branch checked out - use pull instead
                    output.info(f"Remote is a local non-bare repo with '{remote_branch}' checked out.")
                    output.info("Pulling changes into remote to keep working directory in sync...")
                    try:
                        git.pull_from(remote_path, repo_dir, local_branch)
                        # Fetch to update our remote tracking refs so status shows correct state
                        git.fetch(repo_dir)
                        output.success("Push complete (via pull into remote).")
                        return 0
                    except git.GitError as e:
                        output.error(f"Failed to sync changes: {e}")
                        output.info("")
                        output.info("Manual steps to resolve:")
                        output.info(f"  1. cd {remote_path}")
                        output.info(f"  2. git pull {repo_dir} {local_branch}")
                        return 1

    # Standard push for remote URLs or bare repos
    try:
        git.push(repo_dir)
        output.success("Push complete.")
        return 0
    except git.GitError as e:
        # Check if error is due to pushing to checked-out branch
        error_msg = str(e)
        if "refusing to update checked out branch" in error_msg or "branch is currently checked out" in error_msg:
            output.error("Cannot push to a non-bare repository with the target branch checked out.")
            output.info("")
            output.info("Manual steps to resolve:")
            output.info(f"  1. cd {remote_url}")
            output.info(f"  2. git pull {repo_dir} <branch>")
            output.info("")
            output.info("Or convert the remote to a bare repository.")
            return 1
        output.error(str(e))
        return 1


def cmd_commit(args, output: Output) -> int:
    """Execute git commit in overlay repo.

    Before committing, checks for changes to decoded (SOPS-decrypted) files
    and re-encrypts them.
    """
    result = _get_repo_dir_or_error(output)
    if result is None:
        return 1
    repo_dir, root_dir = result

    # Load config to get sops_config path
    cfg_result = _get_config_and_root(output)
    config = cfg_result[0] if cfg_result else None

    # Check for changes to decoded files and re-encrypt
    state = read_state(root_dir)
    encrypted_files = state.get("encrypted_files", {})

    if encrypted_files:
        decoded_dir = get_decoded_dir(root_dir)
        sops_config = sops.get_sops_config_path(repo_dir, config)

        try:
            # Detect which decoded files have changed
            changed = sops.detect_decoded_changes(
                decoded_dir, repo_dir, encrypted_files, sops_config
            )

            if changed:
                output.info(f"Re-encrypting {len(changed)} modified file(s)...")
                # Re-encrypt changed files
                updated = sops.re_encrypt_changed_files(
                    decoded_dir, repo_dir, changed, encrypted_files, sops_config
                )

                if updated:
                    # Stage re-encrypted files
                    git.add(repo_dir, updated)
                    output.info(f"Staged {len(updated)} re-encrypted file(s)")

                    # Update state with new hashes
                    write_state(root_dir, state)

        except sops.SopsError as e:
            output.error(f"Failed to re-encrypt files: {e}")
            output.info("Commit aborted to prevent stale encrypted files.")
            return 1

    try:
        extra_args = []
        if args.all:
            extra_args.append("-a")
        if args.args:
            extra_args.extend(args.args)
        git.commit(repo_dir, message=args.message, args=extra_args if extra_args else None)
        output.success("Commit complete.")
        return 0
    except git.GitError as e:
        output.error(str(e))
        return 1


def cmd_add(args, output: Output) -> int:
    """Execute git add in overlay repo.

    With --encrypt flag or when files match encrypt_patterns in config,
    files are encrypted with SOPS before being added.
    """
    result = _get_repo_dir_or_error(output)
    if result is None:
        return 1
    repo_dir, root_dir = result

    # Load config for encrypt_patterns
    cfg_result = _get_config_and_root(output)
    config = cfg_result[0] if cfg_result else None
    encrypt_patterns = []
    if config and "overlay" in config:
        encrypt_patterns = config["overlay"].get("encrypt_patterns", [])

    from pathlib import Path

    # First pass: separate files that already exist in repo from external files
    # Files already in repo just need to be staged, no copy/encrypt needed
    files_in_repo = []
    files_external = []

    for file_path in args.files:
        path = Path(file_path)

        # For relative paths, check if they exist directly in repo
        if not path.is_absolute():
            repo_path = repo_dir / file_path
            repo_path_enc = repo_dir / (file_path + ".enc")

            if repo_path.exists():
                files_in_repo.append(file_path)
                continue
            elif repo_path_enc.exists():
                files_in_repo.append(file_path + ".enc")
                continue

        # For absolute paths, check if they're inside the repo
        abs_path = path.resolve() if path.is_absolute() else (Path.cwd() / file_path).resolve()
        try:
            rel_to_repo = abs_path.relative_to(repo_dir)
            # File is inside repo
            if abs_path.exists():
                files_in_repo.append(str(rel_to_repo))
            else:
                # Check for .enc version
                enc_path = repo_dir / (str(rel_to_repo) + ".enc")
                if enc_path.exists():
                    files_in_repo.append(str(rel_to_repo) + ".enc")
                else:
                    files_external.append(file_path)
        except ValueError:
            # File is outside repo
            files_external.append(file_path)

    # Stage files that are already in repo
    if files_in_repo:
        try:
            git.add(repo_dir, files_in_repo)
            output.success(f"Staged {len(files_in_repo)} file(s).")
        except git.GitError as e:
            output.error(str(e))
            return 1

    # If no external files, we're done
    if not files_external:
        return 0

    # Determine which external files should be encrypted
    files_to_encrypt = []
    files_to_add_plain = []

    for file_path in files_external:
        should_encrypt = args.encrypt

        # Check against encrypt_patterns if not already flagged
        if not should_encrypt and encrypt_patterns:
            # Get relative path for pattern matching
            abs_path = Path(file_path).resolve()
            try:
                rel_path = abs_path.relative_to(repo_dir)
            except ValueError:
                # File is outside repo_dir, try relative to root_dir
                try:
                    rel_path = abs_path.relative_to(root_dir)
                except ValueError:
                    # File is outside project, use basename
                    rel_path = Path(abs_path.name)
            if matches_any_pattern(str(rel_path), encrypt_patterns):
                should_encrypt = True

        if should_encrypt:
            files_to_encrypt.append(file_path)
        else:
            files_to_add_plain.append(file_path)

    # Handle files that need encryption
    if files_to_encrypt:
        if not sops.is_sops_available():
            output.error(
                "SOPS is not installed. Install it with:\n"
                "  brew install sops      # macOS\n"
                "  apt install sops       # Debian/Ubuntu\n"
                "  choco install sops     # Windows"
            )
            return 1

        sops_config = sops.get_sops_config_path(repo_dir, config)
        decoded_dir = get_decoded_dir(root_dir)
        state = read_state(root_dir)
        encrypted_files = state.get("encrypted_files", {})

        from pathlib import Path
        encrypted_paths = []

        for file_path in files_to_encrypt:
            src_path = Path(file_path)
            if not src_path.is_absolute():
                src_path = Path.cwd() / file_path
            src_path = src_path.resolve()

            if not src_path.exists():
                output.error(f"File not found: {file_path}")
                return 1

            # Determine the encrypted filename and paths
            try:
                rel_path = src_path.relative_to(repo_dir)
            except ValueError:
                # File is outside repo_dir, try relative to root_dir
                try:
                    rel_path = src_path.relative_to(root_dir)
                except ValueError:
                    # File is outside project, use basename
                    rel_path = Path(src_path.name)

            enc_filename = str(rel_path) + ".enc"
            enc_dst = repo_dir / enc_filename
            decoded_dst = decoded_dir / rel_path

            try:
                # Encrypt the file
                sops.encrypt_file(src_path, enc_dst, sops_config)
                output.info(f"Encrypted: {output.path(enc_filename)}")

                # Copy plaintext to decoded dir
                decoded_dst.parent.mkdir(parents=True, exist_ok=True)
                import shutil
                shutil.copy2(src_path, decoded_dst)

                # Update state
                encrypted_files[enc_filename] = {
                    "decoded_path": str(rel_path),
                    "symlink_dst": str(rel_path),
                    "last_encrypted_hash": sops.file_hash(enc_dst),
                }
                encrypted_paths.append(enc_filename)

            except sops.SopsError as e:
                output.error(f"Failed to encrypt {file_path}: {e}")
                return 1

        # Stage encrypted files
        if encrypted_paths:
            try:
                git.add(repo_dir, encrypted_paths)
                output.info(f"Staged {len(encrypted_paths)} encrypted file(s)")
            except git.GitError as e:
                output.error(str(e))
                return 1

        # Update state
        state["encrypted_files"] = encrypted_files
        write_state(root_dir, state)

    # Handle plain files
    if files_to_add_plain:
        from pathlib import Path
        import shutil

        files_to_stage = []

        for file_path in files_to_add_plain:
            src_path = Path(file_path)
            if not src_path.is_absolute():
                src_path = Path.cwd() / file_path
            src_path = src_path.resolve()

            if not src_path.exists():
                output.error(f"File not found: {file_path}")
                return 1

            # Check if file is inside the repo already
            try:
                rel_path = src_path.relative_to(repo_dir)
                # File is already in repo, just add it
                files_to_stage.append(str(rel_path))
            except ValueError:
                # File is outside repo_dir, need to copy it in
                # Try to get relative path from root_dir (project root)
                try:
                    rel_path = src_path.relative_to(root_dir)
                except ValueError:
                    # File is completely outside the project, use basename
                    rel_path = Path(src_path.name)

                # Copy file into repo_dir
                dst_path = repo_dir / rel_path
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_path, dst_path)
                output.info(f"Copied to overlay: {output.path(str(rel_path))}")
                files_to_stage.append(str(rel_path))

        try:
            git.add(repo_dir, files_to_stage)
            output.success("Files staged.")
        except git.GitError as e:
            output.error(str(e))
            return 1
    elif files_to_encrypt:
        output.success("Files encrypted and staged.")

    return 0


def cmd_reset(args, output: Output) -> int:
    """Unstage files from overlay repo."""
    result = _get_repo_dir_or_error(output)
    if result is None:
        return 1
    repo_dir, root_dir = result

    from pathlib import Path

    # Filter out "HEAD" if user passed it (muscle memory from git reset HEAD)
    raw_files = [f for f in (args.files or []) if f != "HEAD"]

    if not raw_files:
        # No files specified, reset all
        try:
            git.reset(repo_dir, None)
            output.success("All files unstaged.")
            return 0
        except git.GitError as e:
            output.error(str(e))
            return 1

    # Convert file paths to repo-relative paths
    files_to_reset = []
    for file_path in raw_files:
        path = Path(file_path)

        # For relative paths, first check if they exist directly in repo
        if not path.is_absolute():
            repo_path = repo_dir / file_path
            repo_path_enc = repo_dir / (file_path + ".enc")

            if repo_path.exists():
                files_to_reset.append(file_path)
                continue
            elif repo_path_enc.exists():
                files_to_reset.append(file_path + ".enc")
                continue

        # Handle absolute paths or paths not found in repo
        abs_path = path.resolve() if path.is_absolute() else (Path.cwd() / file_path).resolve()

        # Try to get path relative to repo_dir
        try:
            rel_path = abs_path.relative_to(repo_dir)
        except ValueError:
            # File is outside repo_dir, try relative to root_dir
            try:
                rel_path = abs_path.relative_to(root_dir)
            except ValueError:
                # Use basename as fallback
                rel_path = Path(abs_path.name)

        # Check if file exists in repo, if not try with .enc suffix
        repo_file = repo_dir / rel_path
        if repo_file.exists():
            files_to_reset.append(str(rel_path))
        elif (repo_dir / (str(rel_path) + ".enc")).exists():
            files_to_reset.append(str(rel_path) + ".enc")
        else:
            # File doesn't exist, try it anyway (git will error if invalid)
            files_to_reset.append(str(rel_path))

    try:
        git.reset(repo_dir, files_to_reset)
        output.success(f"Unstaged {len(files_to_reset)} file(s).")
        return 0
    except git.GitError as e:
        output.error(str(e))
        return 1


def cmd_diff(args, output: Output) -> int:
    """Execute git diff in overlay repo."""
    result = _get_repo_dir_or_error(output)
    if result is None:
        return 1
    repo_dir, _ = result

    return git.diff(repo_dir, args.args if args.args else None).returncode


def cmd_checkout(args, output: Output) -> int:
    """Execute git checkout in overlay repo, then sync."""
    result = _get_repo_dir_or_error(output)
    if result is None:
        return 1
    repo_dir, root_dir = result

    try:
        git.checkout(repo_dir, args.ref)
        output.success(f"Checked out {args.ref}.")
    except git.GitError as e:
        output.error(str(e))
        return 1

    # Sync after checkout
    cfg_result = _get_config_and_root(output)
    if cfg_result is None:
        return 1
    config, _ = cfg_result

    try:
        return sync_overlay(root_dir, config, output=output)
    except OverlayError as e:
        output.error(str(e))
        return 1


def cmd_merge(args, output: Output) -> int:
    """Execute git merge in overlay repo, then sync."""
    result = _get_repo_dir_or_error(output)
    if result is None:
        return 1
    repo_dir, root_dir = result

    try:
        git.merge(repo_dir, args.branch)
        output.success("Merge complete.")
    except git.GitError as e:
        output.error(str(e))
        return 1

    # Sync after merge
    cfg_result = _get_config_and_root(output)
    if cfg_result is None:
        return 1
    config, _ = cfg_result

    try:
        return sync_overlay(root_dir, config, output=output)
    except OverlayError as e:
        output.error(str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
