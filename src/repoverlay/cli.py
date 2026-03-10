"""Command-line interface."""

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from . import __version__, git, sops
from .config import ConfigError, find_config, load_config
from .exclude import update_exclude_file
from .ignore import matches_any_pattern
from .output import Output, set_output
from .intellij import configure_vcs_root, remove_vcs_root
from .overlay import (
    MigrateError,
    OverlayError,
    UncommittedChangesError,
    UnpushedCommitsError,
    cloak_overlay,
    clone_overlay,
    decloak_overlay,
    get_decoded_dir,
    get_repo_dir,
    migrate_file,
    sync_overlay,
    unlink_overlay,
    verify_overlay,
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
        "url",
        nargs="?",
        default=None,
        help="URL of overlay repo (creates .repoverlay.yaml if not present)",
    )
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
    status_parser = subparsers.add_parser("status", help="Show git status of overlay repo")
    status_parser.add_argument("--debug", action="store_true", help="Show debug info for encrypted file detection")
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

    import_parser = subparsers.add_parser("import", help="Import files from main repo into overlay")
    import_parser.add_argument("files", nargs="+", help="Files to import")
    import_parser.add_argument(
        "--encrypt", "-e",
        action="store_true",
        help="Encrypt files with SOPS before importing",
    )
    import_parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview changes without executing",
    )

    restore_parser = subparsers.add_parser("restore", help="Restore files in overlay repo")
    restore_parser.add_argument("--staged", "-S", action="store_true", help="Restore staged changes (unstage)")
    restore_parser.add_argument("files", nargs="+", help="Files to restore")

    reset_parser = subparsers.add_parser("reset", help="Unstage files from overlay repo")
    reset_parser.add_argument("files", nargs="*", help="Files to unstage (default: all staged files)")

    diff_parser = subparsers.add_parser("diff", help="Show diff in overlay repo")
    diff_parser.add_argument("args", nargs=argparse.REMAINDER, help="Additional git diff arguments")

    log_parser = subparsers.add_parser("log", help="Show commit log of overlay repo")
    log_parser.add_argument("args", nargs=argparse.REMAINDER, help="Additional git log arguments")

    checkout_parser = subparsers.add_parser("checkout", help="Checkout ref in overlay repo and sync")
    checkout_parser.add_argument("-b", dest="new_branch", action="store_true", help="Create a new branch")
    checkout_parser.add_argument("ref", help="Branch, tag, or commit to checkout")

    merge_parser = subparsers.add_parser("merge", help="Merge branch in overlay repo and sync")
    merge_parser.add_argument("branch", nargs="?", help="Branch to merge")

    # list command
    subparsers.add_parser("list", help="List files in overlay repo")

    # repair command
    # verify command
    subparsers.add_parser("verify", help="Validate all symlinks are intact and pointing to correct targets")

    repair_parser = subparsers.add_parser("repair", help="Rebuild state from filesystem")
    repair_parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview changes without executing",
    )

    # cloak command
    cloak_parser = subparsers.add_parser(
        "cloak",
        help="Remove decrypted secrets and relink symlinks to encrypted files",
    )
    cloak_parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview changes without executing",
    )

    # decloak command
    decloak_parser = subparsers.add_parser(
        "decloak",
        help="Decrypt secrets and restore symlinks to decrypted files",
    )
    decloak_parser.add_argument(
        "file",
        nargs="?",
        default=None,
        help="Specific file to decloak (decoded or encrypted path); defaults to all",
    )
    decloak_parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview changes without executing",
    )

    # migrate command
    migrate_parser = subparsers.add_parser(
        "migrate",
        help="Move a file between the main repo and the overlay repo",
    )
    migrate_parser.add_argument(
        "file",
        help="File to migrate (path relative to cwd or absolute)",
    )
    migrate_parser.add_argument(
        "--to",
        dest="destination",
        default=None,
        metavar="DEST",
        help="Destination path; defaults to same relative path in destination repo",
    )
    migrate_parser.add_argument(
        "--purge-history",
        action="store_true",
        help="Rewrite source repo history to remove the file (requires git-filter-repo)",
    )
    migrate_parser.add_argument(
        "--encrypt", "-e",
        action="store_true",
        help="Force encryption when moving into overlay (also auto-triggered by encrypt_patterns)",
    )
    migrate_parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview changes without executing",
    )

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
        "status": lambda: cmd_status(args, output),
        "fetch": lambda: cmd_fetch(output),
        "pull": lambda: cmd_pull(args, output),
        "push": lambda: cmd_push(output),
        "commit": lambda: cmd_commit(args, output),
        "add": lambda: cmd_add(args, output),
        "import": lambda: cmd_import(args, output),
        "restore": lambda: cmd_restore(args, output),
        "reset": lambda: cmd_reset(args, output),
        "diff": lambda: cmd_diff(args, output),
        "log": lambda: cmd_log(args, output),
        "checkout": lambda: cmd_checkout(args, output),
        "merge": lambda: cmd_merge(args, output),
        "list": lambda: cmd_list(output),
        "verify": lambda: cmd_verify(output),
        "repair": lambda: cmd_repair(args, output),
        "cloak": lambda: cmd_cloak(args, output),
        "decloak": lambda: cmd_decloak(args, output),
        "migrate": lambda: cmd_migrate(args, output),
    }

    handler = handlers.get(args.command)
    if handler:
        _warn_branch_mismatch(output)
        return handler()

    return 0


def _warn_branch_mismatch(output: Output) -> None:
    """Warn if the overlay repo branch differs from the underlying repo branch."""
    try:
        config_path = find_config()
    except ConfigError:
        return

    root_dir = config_path.parent
    repo_dir = get_repo_dir(root_dir)

    # Only check if overlay repo exists and is a git repo
    if not repo_dir.exists() or not (repo_dir / ".git").exists():
        return

    # Only check if root_dir is a git repo
    if not (root_dir / ".git").exists():
        return

    overlay_branch = git.get_current_branch(repo_dir)
    underlying_branch = git.get_current_branch(root_dir)

    if overlay_branch and underlying_branch and overlay_branch != underlying_branch:
        output.warning(
            f"Overlay repo is on branch '{overlay_branch}' "
            f"but underlying repo is on '{underlying_branch}'"
        )


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
    # If a URL is provided and no config exists, create a minimal .repoverlay.yaml
    if args.url is not None:
        try:
            find_config()
        except ConfigError:
            if not args.dry_run:
                config_path = Path.cwd() / ".repoverlay.yaml"
                config_path.write_text(
                    f"version: 1\noverlay:\n  repo: {args.url}\n"
                )
                output.info(f"Created .repoverlay.yaml with repo: {args.url}")
            else:
                output.info(f"Would create .repoverlay.yaml with repo: {args.url}")

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


def cmd_status(args, output: Output) -> int:
    """Execute git status in overlay repo."""
    debug = getattr(args, 'debug', False)
    result = _get_repo_dir_or_error(output)
    if result is None:
        return 1
    repo_dir, root_dir = result

    # Check if any overlay symlinks are tracked by the main repo
    state = read_state(root_dir)
    symlinks = state.get("symlinks", [])
    if symlinks and (root_dir / ".git").exists():
        tracked = git.get_tracked_files(root_dir, symlinks)
        if tracked:
            output.warning(
                f"Found {len(tracked)} overlay symlink(s) tracked by the main repo!"
            )
            output.info("These should be removed from the main repo's index:")
            cwd = Path.cwd()
            display_paths = []
            for path in tracked:
                abs_path = root_dir / path
                try:
                    rel = os.path.relpath(abs_path, cwd)
                except ValueError:
                    rel = str(abs_path)
                display_paths.append(rel)
                output.info(f"  {rel}")
            output.info("Run: git rm --cached " + " ".join(display_paths))
            output.info("")

    # Check for changes to decoded (encrypted) files
    encrypted_files = state.get("encrypted_files", {})
    if debug:
        output.info(f"[debug] root_dir={root_dir}")
        output.info(f"[debug] repo_dir={repo_dir}")
        output.info(f"[debug] encrypted_files keys={list(encrypted_files.keys())}")
        output.info(f"[debug] encrypted_files count={len(encrypted_files)}")
    if encrypted_files:
        cfg_result = _get_config_and_root(output)
        config = cfg_result[0] if cfg_result else None
        decoded_dir = get_decoded_dir(root_dir)
        sops_config = sops.get_sops_config_path(repo_dir, config)
        if debug:
            output.info(f"[debug] decoded_dir={decoded_dir}, exists={decoded_dir.exists()}")
            output.info(f"[debug] sops_config={sops_config}")

            # Debug: list decoded dir contents
            if decoded_dir.exists():
                decoded_files = list(decoded_dir.rglob("*"))
                output.info(f"[debug] decoded_dir contents: {[str(f.relative_to(decoded_dir)) for f in decoded_files if f.is_file()]}")

            # Debug: list encrypted files in repo
            for enc_path_str, metadata in encrypted_files.items():
                enc_src = repo_dir / enc_path_str
                decoded_path = decoded_dir / metadata.get("decoded_path", "")
                output.info(f"[debug] enc={enc_path_str} exists={enc_src.exists()}, decoded={metadata.get('decoded_path')} exists={decoded_path.exists()}")

        try:
            changed = sops.detect_decoded_changes(
                decoded_dir, repo_dir, encrypted_files, sops_config, debug=debug
            )
            if debug:
                output.info(f"[debug] detect_decoded_changes returned: {changed}")
        except sops.SopsError as e:
            output.error(f"Could not check decoded file changes: {e}")
            changed = []
    else:
        changed = []
    if debug and not encrypted_files:
        output.info("[debug] No encrypted_files in state")

    # Convert changed encrypted paths to decoded paths for display
    extra_unstaged = []
    for enc_path in changed:
        metadata = encrypted_files.get(enc_path, {})
        decoded_name = metadata.get("decoded_path", enc_path)
        extra_unstaged.append(decoded_name)

    # Run git status with decrypted file changes injected
    returncode = git.status(repo_dir, root_dir, extra_unstaged).returncode

    if debug and not changed:
        output.info("[debug] No decoded file changes detected")

    return returncode


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

    # First pass: categorize files
    # - files_in_repo: plain files in repo that just need staging
    # - files_to_reencrypt: decoded files that need re-encryption before staging
    # - files_external: files outside both decoded and repo dirs
    files_in_repo = []
    files_to_reencrypt = []  # List of (enc_name, decoded_path) tuples
    files_external = []
    decoded_dir_files: set[str] = set()  # External files that resolved from decoded_dir (must encrypt)
    decoded_dir = get_decoded_dir(root_dir)

    # Expand any directories into their constituent files first.
    # source_dir_map tracks which directory each expanded file came from so that
    # encrypt_patterns can be matched relative to the source directory, not just root_dir.
    expanded_files = []
    source_dir_map: dict[str, Path | None] = {}
    for file_path in args.files:
        path = Path(file_path)
        abs_path = path.resolve() if path.is_absolute() else (Path.cwd() / file_path).resolve()
        if abs_path.is_dir():
            for child in abs_path.rglob("*"):
                if child.is_file():
                    child_str = str(child)
                    expanded_files.append(child_str)
                    source_dir_map[child_str] = abs_path
        else:
            expanded_files.append(file_path)
            source_dir_map[file_path] = None

    for file_path in expanded_files:
        path = Path(file_path)

        # Resolve to absolute path to handle all path types uniformly
        abs_path = path.resolve() if path.is_absolute() else (Path.cwd() / file_path).resolve()

        # Check if the resolved path is inside the decoded directory
        # (e.g., file is a symlink to .repoverlay/decoded/something, or user specified
        # a path like ../../.repoverlay/decoded/...)
        # If so, we need to re-encrypt before staging. Plaintext decoded files must
        # NEVER be copied into repo_dir, so always continue after this check.
        try:
            rel_to_decoded = abs_path.relative_to(decoded_dir)
            enc_name = str(rel_to_decoded) + ".enc"
            if (repo_dir / enc_name).exists():
                files_to_reencrypt.append((enc_name, abs_path))
            else:
                # No .enc yet — file came from decoded dir, must be encrypted
                files_external.append(file_path)
                decoded_dir_files.add(file_path)
            continue
        except ValueError:
            pass

        # Check if path is inside the repo directory (absolute path resolves there)
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
            continue
        except ValueError:
            pass

        # For relative paths, also check if they exist directly in repo
        # (user may specify repo-relative paths like "secrets/db.yaml")
        if not path.is_absolute():
            repo_path = repo_dir / file_path
            repo_path_enc = repo_dir / (file_path + ".enc")

            if repo_path.exists():
                files_in_repo.append(file_path)
                continue
            elif repo_path_enc.exists():
                files_in_repo.append(file_path + ".enc")
                continue

        # File is outside both decoded and repo directories - it's external
        files_external.append(file_path)

    # Re-encrypt decoded files before staging
    if files_to_reencrypt:
        cfg_result = _get_config_and_root(output)
        config = cfg_result[0] if cfg_result else None
        sops_config = sops.get_sops_config_path(repo_dir, config)
        state = read_state(root_dir)
        encrypted_files = state.get("encrypted_files", {})

        reencrypted_paths = []
        for enc_name, decoded_path in files_to_reencrypt:
            enc_dst = repo_dir / enc_name
            try:
                sops.encrypt_file(decoded_path, enc_dst, sops_config)
                output.info(f"Re-encrypted: {output.path(enc_name)}")
                reencrypted_paths.append(enc_name)

                # Update state with new hashes (both encrypted and decoded)
                rel_decoded = str(decoded_path.relative_to(decoded_dir))
                encrypted_files[enc_name] = {
                    "decoded_path": rel_decoded,
                    "symlink_dst": rel_decoded,
                    "last_encrypted_hash": sops.file_hash(enc_dst),
                    "last_decoded_hash": sops.file_hash(decoded_path),
                }
            except sops.SopsError as e:
                output.error(f"Failed to re-encrypt {enc_name}: {e}")
                return 1

        # Update state
        if reencrypted_paths:
            state["encrypted_files"] = encrypted_files
            write_state(root_dir, state)
            files_in_repo.extend(reencrypted_paths)

    # Stage files that are already in repo (including re-encrypted ones)
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
        # Files that came from the decoded directory must always be encrypted —
        # plaintext decoded content must never be copied into repo_dir.
        should_encrypt = args.encrypt or (file_path in decoded_dir_files)

        # Check against encrypt_patterns if not already flagged
        if not should_encrypt and encrypt_patterns:
            abs_path = Path(file_path).resolve()
            # Build candidate paths for pattern matching, most specific first:
            # 1. Relative to the source directory (when file came from a directory arg)
            # 2. Relative to root_dir
            # 3. Basename fallback
            candidates = []
            source_dir = source_dir_map.get(file_path)
            if source_dir is not None:
                try:
                    candidates.append(abs_path.relative_to(source_dir))
                except ValueError:
                    pass
            try:
                candidates.append(abs_path.relative_to(root_dir))
            except ValueError:
                pass
            if not candidates:
                candidates.append(Path(abs_path.name))
            if any(matches_any_pattern(str(p), encrypt_patterns) for p in candidates):
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
                # Check if file is inside decoded dir (e.g., symlink target)
                # If so, use the decoded-relative path to find the correct .enc file
                try:
                    rel_path = src_path.relative_to(decoded_dir)
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

                # Copy plaintext to decoded dir (skip if src is already the decoded file)
                decoded_dst.parent.mkdir(parents=True, exist_ok=True)
                import shutil
                if src_path.resolve() != decoded_dst.resolve():
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

        # Update state — also add new symlink destinations to the symlinks list
        # so the main repo's git exclude is kept in sync and doesn't show decoded
        # files as untracked in the base repo's git status.
        state["encrypted_files"] = encrypted_files
        existing_symlinks = set(state.get("symlinks", []))
        for enc_name in encrypted_paths:
            symlink_dst = encrypted_files[enc_name].get("symlink_dst")
            if symlink_dst:
                existing_symlinks.add(symlink_dst)
        state["symlinks"] = sorted(existing_symlinks)
        write_state(root_dir, state)
        try:
            update_exclude_file(root_dir, state["symlinks"])
        except Exception:
            pass

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
                # Check if inside decoded dir first (e.g., symlink target)
                try:
                    rel_path = src_path.relative_to(decoded_dir)
                except ValueError:
                    # Try relative to root_dir (project root)
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


def cmd_import(args, output: Output) -> int:
    """Import files from main repo into overlay repo.

    Copies files into the overlay repo, removes them from the main repo index,
    creates symlinks, and updates state.
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

    # Load existing state
    state = read_state(root_dir)
    existing_symlinks = state.get("symlinks", [])
    existing_dirs = state.get("created_directories", [])
    encrypted_files = state.get("encrypted_files", {})

    from pathlib import Path
    import shutil
    import os

    decoded_dir = get_decoded_dir(root_dir)
    dry_run = args.dry_run

    new_symlinks = []
    new_dirs = []
    files_to_git_rm = []
    files_to_git_add = []

    # Collect all files to process
    all_files = []
    for file_arg in args.files:
        path = Path(file_arg)
        if not path.is_absolute():
            abs_path = (Path.cwd() / file_arg).resolve()
        else:
            abs_path = path.resolve()

        # Resolve to root_dir-relative path
        try:
            rel_path = abs_path.relative_to(root_dir)
        except ValueError:
            output.error(f"File is outside the project root: {file_arg}")
            return 1

        # Verify the file exists
        if not abs_path.exists():
            output.error(f"File not found: {file_arg}")
            return 1

        # If directory, collect all files recursively
        if abs_path.is_dir():
            for child in abs_path.rglob("*"):
                if child.is_file():
                    all_files.append(child.relative_to(root_dir))
        else:
            all_files.append(rel_path)

    if not all_files:
        output.warning("No files to import.")
        return 0

    # Determine which files are tracked BEFORE we modify anything
    all_file_strs = [str(f) for f in all_files]
    tracked_files = set(git.get_tracked_files(root_dir, all_file_strs)) if not dry_run else set()

    sops_config = None
    if args.encrypt or encrypt_patterns:
        sops_config = sops.get_sops_config_path(repo_dir, config)

    for rel_path in all_files:
        rel_str = str(rel_path)
        abs_path = root_dir / rel_path

        # Check if already in overlay
        if (repo_dir / rel_path).exists():
            output.warning(f"Skipping {rel_str} - already exists in overlay repo")
            continue

        # Determine if it should be encrypted
        should_encrypt = args.encrypt
        if not should_encrypt and encrypt_patterns:
            if matches_any_pattern(rel_str, encrypt_patterns):
                should_encrypt = True

        if dry_run:
            if should_encrypt:
                output.info(f"{output.dry_run_prefix()} Would import and encrypt {output.path(rel_str)}")
            else:
                output.info(f"{output.dry_run_prefix()} Would import {output.path(rel_str)}")
            continue

        if should_encrypt:
            # Encrypt the file into the overlay repo
            if not sops.is_sops_available():
                output.error(
                    "SOPS is not installed. Install it with:\n"
                    "  brew install sops      # macOS\n"
                    "  apt install sops       # Debian/Ubuntu\n"
                    "  choco install sops     # Windows"
                )
                return 1

            enc_filename = rel_str + ".enc"
            enc_dst = repo_dir / enc_filename
            decoded_dst = decoded_dir / rel_path

            try:
                # Ensure parent dirs exist
                enc_dst.parent.mkdir(parents=True, exist_ok=True)
                sops.encrypt_file(abs_path, enc_dst, sops_config)
                output.info(f"Encrypted: {output.path(enc_filename)}")

                # Copy plaintext to decoded dir
                decoded_dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(abs_path, decoded_dst)

                # Track encrypted file state
                encrypted_files[enc_filename] = {
                    "decoded_path": rel_str,
                    "symlink_dst": rel_str,
                    "last_encrypted_hash": sops.file_hash(enc_dst),
                }
                files_to_git_add.append(enc_filename)

            except sops.SopsError as e:
                output.error(f"Failed to encrypt {rel_str}: {e}")
                return 1

            # Create symlink to decoded file
            dst_path = root_dir / rel_path
            src_path = decoded_dir / rel_path
            rel_symlink = os.path.relpath(src_path, dst_path.parent)

        else:
            # Copy file to overlay repo (preserving directory structure)
            dst_in_repo = repo_dir / rel_path
            dst_in_repo.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(abs_path, dst_in_repo)
            output.info(f"Copied to overlay: {output.path(rel_str)}")
            files_to_git_add.append(rel_str)

            # Create symlink to overlay repo file
            dst_path = root_dir / rel_path
            src_path = repo_dir / rel_path
            rel_symlink = os.path.relpath(src_path, dst_path.parent)

        # git rm --cached from main repo
        files_to_git_rm.append(rel_str)

        # Remove the original file and create symlink
        dst_path.unlink()
        dst_path.symlink_to(rel_symlink)
        new_symlinks.append(rel_str)
        output.created(f"{rel_str} (symlink)")

        # Track created parent directories
        parent = dst_path.parent
        if parent != root_dir:
            rel_parent = parent.relative_to(root_dir)
            for i in range(len(rel_parent.parts)):
                dir_path = Path(*rel_parent.parts[:i + 1])
                dir_str = str(dir_path)
                if dir_str not in existing_dirs and dir_str not in new_dirs:
                    new_dirs.append(dir_str)

    if dry_run:
        return 0

    if not files_to_git_rm and not files_to_git_add:
        output.warning("No files were imported.")
        return 0

    # git rm --cached from main repo index (only for files that were tracked)
    if files_to_git_rm:
        tracked = [f for f in files_to_git_rm if f in tracked_files]
        if tracked:
            try:
                git.rm(root_dir, tracked, cached=True)
                output.info(f"Removed {len(tracked)} file(s) from main repo index")
            except git.GitError as e:
                output.error(f"Failed to remove from main repo index: {e}")
                return 1
        untracked_count = len(files_to_git_rm) - len(tracked)
        if untracked_count:
            output.info(f"Skipped {untracked_count} untracked file(s) (not in main repo index)")

    # git add in overlay repo
    if files_to_git_add:
        try:
            git.add(repo_dir, files_to_git_add)
            output.info(f"Staged {len(files_to_git_add)} file(s) in overlay repo")
        except git.GitError as e:
            output.error(f"Failed to stage in overlay repo: {e}")
            return 1

    # Update state
    all_symlinks = list(set(existing_symlinks + new_symlinks))
    all_dirs = list(set(existing_dirs + new_dirs))

    write_state(root_dir, {
        "symlinks": all_symlinks,
        "created_directories": all_dirs,
        "encrypted_files": encrypted_files,
    })

    # Update git exclude
    try:
        update_exclude_file(root_dir, all_symlinks)
    except Exception:
        pass

    output.success(f"Imported {len(new_symlinks)} file(s) into overlay repo.")
    return 0


def cmd_restore(args, output: Output) -> int:
    """Execute git restore in overlay repo."""
    result = _get_repo_dir_or_error(output)
    if result is None:
        return 1
    repo_dir, root_dir = result

    from pathlib import Path

    files_to_restore = []

    for file_path in args.files:
        path = Path(file_path)

        # For relative paths, first check if they exist directly in repo
        if not path.is_absolute():
            repo_path = repo_dir / file_path
            repo_path_enc = repo_dir / (file_path + ".enc")

            if repo_path.exists():
                files_to_restore.append(file_path)
                continue
            elif repo_path_enc.exists():
                files_to_restore.append(file_path + ".enc")
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
            files_to_restore.append(str(rel_path))
        elif (repo_dir / (str(rel_path) + ".enc")).exists():
            files_to_restore.append(str(rel_path) + ".enc")
        else:
            # File doesn't exist, try it anyway (git will error if invalid)
            files_to_restore.append(str(rel_path))

    try:
        git.restore(repo_dir, files_to_restore, staged=args.staged)
        action = "Unstaged" if args.staged else "Restored"
        output.success(f"{action} {len(files_to_restore)} file(s).")
        return 0
    except git.GitError as e:
        output.error(str(e))
        return 1


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
    from pathlib import Path

    result = _get_repo_dir_or_error(output)
    if result is None:
        return 1
    repo_dir, root_dir = result

    returncode = git.diff(repo_dir, args.args if args.args else None).returncode

    # Show diffs for modified decoded (encrypted) files
    state = read_state(root_dir)
    encrypted_files = state.get("encrypted_files", {})
    if encrypted_files:
        cfg_result = _get_config_and_root(output)
        config = cfg_result[0] if cfg_result else None
        decoded_dir = get_decoded_dir(root_dir)
        sops_config = sops.get_sops_config_path(repo_dir, config)

        try:
            changed = sops.detect_decoded_changes(
                decoded_dir, repo_dir, encrypted_files, sops_config
            )
            if changed:
                output.warning("\nChanges not staged for commit (decrypted files):")
                with tempfile.TemporaryDirectory() as tmp_dir:
                    tmp_path = Path(tmp_dir)
                    for enc_path in changed:
                        metadata = encrypted_files.get(enc_path, {})
                        decoded_name = metadata.get("decoded_path", enc_path)
                        decoded_file = decoded_dir / decoded_name
                        enc_src = repo_dir / enc_path

                        if not decoded_file.exists() or not enc_src.exists():
                            continue

                        # Decrypt encrypted source to temp file for comparison
                        tmp_decrypted = tmp_path / decoded_name
                        tmp_decrypted.parent.mkdir(parents=True, exist_ok=True)
                        try:
                            sops.decrypt_file(enc_src, tmp_decrypted, sops_config)
                        except sops.SopsError as e:
                            output.error(f"Could not decrypt {enc_path} for diff: {e}")
                            continue

                        # Run diff between decrypted original and current decoded file
                        diff_result = subprocess.run(
                            ["diff", "-u",
                             "--label", f"a/{decoded_name} (encrypted)",
                             "--label", f"b/{decoded_name} (decoded)",
                             str(tmp_decrypted), str(decoded_file)],
                            capture_output=True,
                            text=True,
                        )
                        if diff_result.stdout:
                            print(diff_result.stdout)

        except sops.SopsError as e:
            output.error(f"Could not check decoded file changes: {e}")

    return returncode


def cmd_log(args, output: Output) -> int:
    """Execute git log in overlay repo."""
    result = _get_repo_dir_or_error(output)
    if result is None:
        return 1
    repo_dir, _ = result

    return git.log(repo_dir, args.args if args.args else None).returncode


def cmd_checkout(args, output: Output) -> int:
    """Execute git checkout in overlay repo, then sync."""
    result = _get_repo_dir_or_error(output)
    if result is None:
        return 1
    repo_dir, root_dir = result

    try:
        git.checkout(repo_dir, args.ref, new_branch=args.new_branch)
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


def cmd_verify(output: Output) -> int:
    """Validate all symlinks are intact and correct."""
    result = _get_repo_dir_or_error(output)
    if result is None:
        return 1
    repo_dir, root_dir = result

    issues = verify_overlay(root_dir, output=output)
    return 1 if issues else 0


def cmd_repair(args, output: Output) -> int:
    """Rebuild state from filesystem.

    Scans the overlay repo and decoded directory to rebuild the state file.
    Useful when state is corrupted or destroyed.
    """
    import os
    from pathlib import Path

    result = _get_repo_dir_or_error(output)
    if result is None:
        return 1
    repo_dir, root_dir = result

    decoded_dir = get_decoded_dir(root_dir)
    dry_run = args.dry_run

    output.info("Scanning filesystem to rebuild state...")

    # 1. Scan for encrypted files in the repo
    encrypted_files = {}
    enc_file_paths = sops.scan_encrypted_files(repo_dir)

    if enc_file_paths:
        output.info(f"Found {len(enc_file_paths)} encrypted file(s)")

        # Load config for SOPS config path
        cfg_result = _get_config_and_root(output)
        config = cfg_result[0] if cfg_result else None
        sops_config = sops.get_sops_config_path(repo_dir, config)

        for enc_path in enc_file_paths:
            enc_path_str = str(enc_path)
            enc_src = repo_dir / enc_path
            decoded_name = sops.get_decoded_path(enc_path_str)
            decoded_file = decoded_dir / decoded_name

            metadata = {
                "decoded_path": decoded_name,
                "symlink_dst": decoded_name,
                "last_encrypted_hash": sops.file_hash(enc_src),
            }

            # If decoded file exists, compute its hash
            if decoded_file.exists():
                metadata["last_decoded_hash"] = sops.file_hash(decoded_file)
                output.info(f"  {enc_path_str} -> {decoded_name} (decoded exists)")
            else:
                # Try to decrypt it
                if not dry_run and sops.is_sops_available():
                    try:
                        decoded_file.parent.mkdir(parents=True, exist_ok=True)
                        sops.decrypt_file(enc_src, decoded_file, sops_config)
                        metadata["last_decoded_hash"] = sops.file_hash(decoded_file)
                        output.info(f"  {enc_path_str} -> {decoded_name} (decrypted)")
                    except sops.SopsError as e:
                        output.warning(f"  {enc_path_str} -> could not decrypt: {e}")
                else:
                    output.info(f"  {enc_path_str} -> {decoded_name} (not decrypted)")

            encrypted_files[enc_path_str] = metadata

    # 2. Scan for symlinks in the root directory pointing to overlay repo or decoded dir
    symlinks = []
    created_dirs = set()

    def scan_for_symlinks(directory: Path, base: Path):
        """Recursively scan for symlinks pointing to overlay."""
        for item in directory.iterdir():
            if item.name.startswith("."):
                # Skip hidden directories like .git, .repoverlay
                continue

            if item.is_symlink():
                target = item.resolve()
                # Check if symlink points to repo_dir or decoded_dir
                try:
                    target.relative_to(repo_dir)
                    is_overlay_symlink = True
                except ValueError:
                    try:
                        target.relative_to(decoded_dir)
                        is_overlay_symlink = True
                    except ValueError:
                        is_overlay_symlink = False

                if is_overlay_symlink:
                    rel_path = str(item.relative_to(base))
                    symlinks.append(rel_path)
                    # Track parent directories
                    parent = item.parent
                    while parent != base:
                        try:
                            rel_parent = str(parent.relative_to(base))
                            created_dirs.add(rel_parent)
                        except ValueError:
                            break
                        parent = parent.parent

            elif item.is_dir():
                scan_for_symlinks(item, base)

    scan_for_symlinks(root_dir, root_dir)

    output.info(f"Found {len(symlinks)} symlink(s) pointing to overlay")
    for sl in symlinks:
        output.info(f"  {sl}")

    if created_dirs:
        output.info(f"Found {len(created_dirs)} directory(ies) created for symlinks")

    # 3. Build new state
    new_state = {
        "symlinks": sorted(symlinks),
        "created_directories": sorted(created_dirs),
        "encrypted_files": encrypted_files,
    }

    if dry_run:
        output.info(f"{output.dry_run_prefix()} Would write state with:")
        output.info(f"  {len(symlinks)} symlinks")
        output.info(f"  {len(created_dirs)} directories")
        output.info(f"  {len(encrypted_files)} encrypted files")
        return 0

    # 4. Write state
    write_state(root_dir, new_state)
    output.success(f"State rebuilt: {len(symlinks)} symlinks, {len(encrypted_files)} encrypted files")

    return 0


def cmd_cloak(args, output: Output) -> int:
    """Remove decrypted secrets and relink symlinks to encrypted files."""
    result = _get_config_and_root(output)
    if result is None:
        return 1
    _config, root_dir = result

    try:
        cloak_overlay(root_dir, dry_run=args.dry_run, output=output)
    except OverlayError as e:
        output.error(str(e))
        return 1

    return 0


def cmd_decloak(args, output: Output) -> int:
    """Decrypt secrets and restore symlinks to decrypted files."""
    result = _get_config_and_root(output)
    if result is None:
        return 1
    config, root_dir = result

    try:
        decloak_overlay(
            root_dir,
            config,
            file=getattr(args, "file", None),
            dry_run=args.dry_run,
            output=output,
        )
    except OverlayError as e:
        output.error(str(e))
        return 1

    return 0


def cmd_migrate(args, output: Output) -> int:
    """Move a file between the main repo and the overlay repo."""
    result = _get_config_and_root(output)
    if result is None:
        return 1
    config, root_dir = result

    try:
        migrate_file(
            root_dir,
            config,
            args.file,
            args.destination,
            purge_history=args.purge_history,
            encrypt=args.encrypt,
            dry_run=args.dry_run,
            output=output,
        )
    except MigrateError as e:
        output.error(str(e))
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
