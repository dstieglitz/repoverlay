"""Command-line interface."""

import argparse
import sys

from . import __version__, git
from .config import ConfigError, find_config, load_config
from .output import Output, set_output
from .overlay import (
    OverlayError,
    clone_overlay,
    get_repo_dir,
    sync_overlay,
    unlink_overlay,
)


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

    # unlink command
    unlink_parser = subparsers.add_parser("unlink", help="Remove all symlinks and clean up")
    unlink_parser.add_argument(
        "--remove-repo",
        action="store_true",
        help="Also remove .repoverlay/ directory",
    )
    unlink_parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Preview changes without executing",
    )

    # Git passthrough commands
    subparsers.add_parser("status", help="Show git status of overlay repo")
    subparsers.add_parser("fetch", help="Fetch updates from overlay remote")
    subparsers.add_parser("pull", help="Pull updates and sync symlinks")
    subparsers.add_parser("push", help="Push overlay repo changes")

    commit_parser = subparsers.add_parser("commit", help="Commit changes in overlay repo")
    commit_parser.add_argument("-m", "--message", help="Commit message")
    commit_parser.add_argument("args", nargs="*", help="Additional git commit arguments")

    add_parser = subparsers.add_parser("add", help="Add files to overlay repo staging")
    add_parser.add_argument("files", nargs="+", help="Files to add")

    diff_parser = subparsers.add_parser("diff", help="Show diff in overlay repo")
    diff_parser.add_argument("args", nargs=argparse.REMAINDER, help="Additional git diff arguments")

    checkout_parser = subparsers.add_parser("checkout", help="Checkout ref in overlay repo and sync")
    checkout_parser.add_argument("ref", help="Branch, tag, or commit to checkout")

    merge_parser = subparsers.add_parser("merge", help="Merge branch in overlay repo and sync")
    merge_parser.add_argument("branch", nargs="?", help="Branch to merge")

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
        "pull": lambda: cmd_pull(output),
        "push": lambda: cmd_push(output),
        "commit": lambda: cmd_commit(args, output),
        "add": lambda: cmd_add(args, output),
        "diff": lambda: cmd_diff(args, output),
        "checkout": lambda: cmd_checkout(args, output),
        "merge": lambda: cmd_merge(args, output),
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
        return exit_code
    except OverlayError as e:
        output.error(str(e))
        return 1


def cmd_unlink(args, output: Output) -> int:
    """Execute the unlink command."""
    try:
        config_path = find_config()
    except ConfigError as e:
        output.error(str(e))
        return 1

    root_dir = config_path.parent
    remove_repo = args.remove_repo

    # If not using --remove-repo and not dry-run, prompt the user
    if not remove_repo and not args.dry_run:
        overlay_dir = root_dir / ".repoverlay"
        if overlay_dir.exists() and sys.stdin.isatty():
            try:
                response = input("Remove .repoverlay/ directory? [y/N] ").strip().lower()
                remove_repo = response in ("y", "yes")
            except (EOFError, KeyboardInterrupt):
                print()  # Newline after ^C
                remove_repo = False

    try:
        unlink_overlay(
            root_dir,
            remove_repo=remove_repo,
            dry_run=args.dry_run,
            output=output,
        )
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


def cmd_pull(output: Output) -> int:
    """Execute git pull in overlay repo, then sync."""
    result = _get_repo_dir_or_error(output)
    if result is None:
        return 1
    repo_dir, root_dir = result

    try:
        git.pull(repo_dir)
        output.success("Pull complete.")
    except git.GitError as e:
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


def cmd_push(output: Output) -> int:
    """Execute git push in overlay repo."""
    result = _get_repo_dir_or_error(output)
    if result is None:
        return 1
    repo_dir, _ = result

    try:
        git.push(repo_dir)
        output.success("Push complete.")
        return 0
    except git.GitError as e:
        output.error(str(e))
        return 1


def cmd_commit(args, output: Output) -> int:
    """Execute git commit in overlay repo."""
    result = _get_repo_dir_or_error(output)
    if result is None:
        return 1
    repo_dir, _ = result

    try:
        git.commit(repo_dir, message=args.message, args=args.args if args.args else None)
        output.success("Commit complete.")
        return 0
    except git.GitError as e:
        output.error(str(e))
        return 1


def cmd_add(args, output: Output) -> int:
    """Execute git add in overlay repo."""
    result = _get_repo_dir_or_error(output)
    if result is None:
        return 1
    repo_dir, _ = result

    try:
        git.add(repo_dir, args.files)
        output.success("Files staged.")
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
