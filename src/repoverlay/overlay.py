"""Overlay cloning and symlink creation."""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from . import git
from . import sops
from .exclude import update_exclude_file
from .ignore import filter_mappings, load_ignore_patterns, matches_any_pattern
from .output import Output, get_output
from .state import read_state, write_state
from .validation import ValidationError, validate_mappings
from .warnings import check_gitignore_conflicts


class OverlayError(Exception):
    """Raised when overlay operations fail."""
    pass


class MigrateError(OverlayError):
    """Raised when migrate operations fail."""
    pass


def get_overlay_dir(root_dir: Path) -> Path:
    """Get path to .repoverlay/ directory.

    Args:
        root_dir: Root directory of main repo.

    Returns:
        Path to .repoverlay/
    """
    return root_dir / ".repoverlay"


def get_repo_dir(root_dir: Path) -> Path:
    """Get path to cloned overlay repo.

    Args:
        root_dir: Root directory of main repo.

    Returns:
        Path to .repoverlay/repo/
    """
    return get_overlay_dir(root_dir) / "repo"


def get_decoded_dir(root_dir: Path) -> Path:
    """Get path to decoded files directory.

    This is where SOPS-decrypted files are stored.

    Args:
        root_dir: Root directory of main repo.

    Returns:
        Path to .repoverlay/decoded/
    """
    return get_overlay_dir(root_dir) / "decoded"


def _is_local_path(repo: str) -> bool:
    """Check if repo is a local path rather than a git URL.

    Args:
        repo: Repository URL or path

    Returns:
        True if it's a local filesystem path
    """
    # Git URLs typically have : for SSH or :// for protocols
    if "://" in repo or (repo.startswith("git@") and ":" in repo):
        return False
    # It's a local path (absolute or relative)
    return True


def _generate_mappings_from_repo(
    repo_dir: Path,
    encrypted_files: dict[str, dict[str, str]] | None = None,
    exclude_paths: set[str] | None = None,
) -> list[dict]:
    """Generate mappings from all files in a repository.

    Creates mappings where src and dst are the same path for each file.
    For encrypted files, maps to decoded versions instead.

    Args:
        repo_dir: Path to the overlay repository
        encrypted_files: Optional dict of encrypted file metadata from SOPS decryption
        exclude_paths: Optional set of paths to exclude from mappings

    Returns:
        List of mapping dicts with src/dst keys
    """
    mappings = []
    encrypted_files = encrypted_files or {}
    exclude_paths = exclude_paths or set()

    for path in repo_dir.rglob("*"):
        # Skip directories (we only link files, not dirs directly)
        # Also skip .git directory and .config directory (holds .sops.yaml)
        if path.is_dir():
            continue
        rel_path = path.relative_to(repo_dir)
        if rel_path.parts[0] in (".git", ".config"):
            continue
        path_str = str(rel_path)

        # For encrypted files, don't create mappings - they're handled separately
        # as symlinks to decoded files
        if path_str in encrypted_files or path_str in exclude_paths:
            continue

        mappings.append({"src": path_str, "dst": path_str})
    return mappings


def clone_overlay(
    root_dir: Path,
    config: dict[str, Any],
    *,
    force: bool = False,
    dry_run: bool = False,
    output: Output | None = None,
) -> None:
    """Clone overlay repo and create symlinks.

    Args:
        root_dir: Root directory of main repo (contains .repoverlay.yaml).
        config: Validated config dict.
        force: Overwrite existing .repoverlay/repo/
        dry_run: Preview changes without making them
        output: Output handler

    Raises:
        OverlayError: If operation fails.
    """
    if output is None:
        output = get_output()

    overlay_dir = get_overlay_dir(root_dir)
    repo_dir = get_repo_dir(root_dir)
    overlay_config = config["overlay"]
    repo_url = overlay_config["repo"]
    is_local = _is_local_path(repo_url)

    # Check if already cloned
    if repo_dir.exists():
        if force:
            # Safety checks before removing repo
            if (repo_dir / ".git").exists():
                # Check for unpushed commits - hard block
                has_unpushed, commit_count = git.has_unpushed_commits(repo_dir)
                if has_unpushed:
                    raise UnpushedCommitsError(
                        f"Cannot force clone - there are {commit_count} unpushed commit(s) in the overlay repo.\n"
                        "Run 'repoverlay push' first, or remove the commits with 'git reset'.",
                        commit_count,
                    )

                # Check for uncommitted changes - hard block
                has_uncommitted, changed_files = git.has_uncommitted_changes(repo_dir)
                if has_uncommitted:
                    raise UncommittedChangesError(
                        "Cannot force clone - uncommitted changes detected in overlay repo.\n"
                        "Commit or discard changes first.",
                        changed_files,
                    )

            if dry_run:
                output.info(f"{output.dry_run_prefix()} Would remove {output.path(str(repo_dir))}")
            else:
                shutil.rmtree(repo_dir)
        else:
            raise OverlayError("Already cloned. Remove .repoverlay/ to re-clone or use --force")

    # For dry run with no mappings, we need to clone/copy first to generate mappings
    # but we can't do that in dry run mode, so we show a message
    explicit_mappings = overlay_config.get("mappings")

    if dry_run:
        action = "copy" if is_local else "clone"
        output.info(f"{output.dry_run_prefix()} Would {action} {output.path(repo_url)}")
        if explicit_mappings:
            # Validate explicit mappings
            try:
                validate_mappings(explicit_mappings)
            except ValidationError as e:
                raise OverlayError(str(e))
            ignore_patterns = load_ignore_patterns(root_dir)
            mappings = filter_mappings(explicit_mappings, ignore_patterns)
            for mapping in mappings:
                output.info(f"{output.dry_run_prefix()} Would create symlink {output.path(mapping['dst'])}")
        else:
            output.info(f"{output.dry_run_prefix()} Would create symlinks for all files in overlay")
        return

    # Create .repoverlay directory
    overlay_dir.mkdir(parents=True, exist_ok=True)

    # Clone or copy the repo
    if is_local:
        # Local path - could be a git repo or plain directory
        local_path = Path(repo_url)
        if not local_path.is_absolute():
            local_path = (root_dir / local_path).resolve()
        if not local_path.exists():
            raise OverlayError(f"Local overlay path not found: {repo_url}")
        if not local_path.is_dir():
            raise OverlayError(f"Local overlay path is not a directory: {repo_url}")

        # Check if it's a git repo
        if (local_path / ".git").exists():
            # Clone the local git repo
            try:
                git.clone(str(local_path), repo_dir)
            except git.GitError as e:
                raise OverlayError(str(e))
            # Checkout ref if specified
            if "ref" in overlay_config:
                try:
                    git.checkout(repo_dir, overlay_config["ref"])
                except git.GitError as e:
                    raise OverlayError(str(e))
        else:
            # Plain directory - copy contents
            shutil.copytree(local_path, repo_dir)
    else:
        # Git URL - clone
        try:
            git.clone(repo_url, repo_dir)
        except git.GitError as e:
            raise OverlayError(str(e))

        # Checkout ref if specified
        if "ref" in overlay_config:
            try:
                git.checkout(repo_dir, overlay_config["ref"])
            except git.GitError as e:
                raise OverlayError(str(e))

    # Handle SOPS encrypted files
    decoded_dir = get_decoded_dir(root_dir)
    encrypted_files: dict[str, dict[str, str]] = {}
    encrypted_symlinks: list[str] = []

    # Scan for encrypted files
    enc_file_paths = sops.scan_encrypted_files(repo_dir)
    if enc_file_paths:
        # Find SOPS config
        sops_config = sops.get_sops_config_path(repo_dir, config)
        if sops_config:
            output.info(f"Found SOPS config: {output.path(str(sops_config.relative_to(repo_dir)))}")

        try:
            # Decrypt all encrypted files
            output.info("Decrypting SOPS-encrypted files...")
            encrypted_files = sops.decrypt_all_files(repo_dir, decoded_dir, sops_config)
            output.info(f"Decrypted {len(encrypted_files)} file(s)")
        except sops.SopsNotAvailableError as e:
            raise OverlayError(str(e))
        except sops.SopsDecryptionError as e:
            raise OverlayError(str(e))

    # Generate mappings if not provided
    if explicit_mappings:
        mappings = explicit_mappings
        # Validate explicit mappings
        try:
            validate_mappings(mappings)
        except ValidationError as e:
            raise OverlayError(str(e))
    else:
        mappings = _generate_mappings_from_repo(repo_dir, encrypted_files)

    # Load ignore patterns and filter mappings
    ignore_patterns = load_ignore_patterns(root_dir)
    mappings = filter_mappings(mappings, ignore_patterns)

    # Create symlinks for regular files
    symlinks_created, dirs_created, skipped = _create_symlinks(root_dir, repo_dir, mappings, output, force=force)

    # Create symlinks for decoded (encrypted) files
    if encrypted_files:
        for enc_path, metadata in encrypted_files.items():
            decoded_path = metadata["decoded_path"]
            # For encrypted files, dst is the decoded path (without .enc suffix)
            dst = decoded_path
            src_path = decoded_dir / decoded_path
            dst_path = root_dir / dst

            # Check destination
            if dst_path.exists() or dst_path.is_symlink():
                if force:
                    if dst_path.is_symlink():
                        dst_path.unlink()
                    elif dst_path.is_file():
                        dst_path.unlink()
                    else:
                        shutil.rmtree(dst_path)
                else:
                    # Skip existing files with a warning instead of erroring
                    output.warning(f"Skipping {dst} - destination already exists (use --force to overwrite)")
                    continue

            # Create parent directories if needed
            parent = dst_path.parent
            if not parent.exists():
                parent.mkdir(parents=True, exist_ok=True)
                rel_parent = parent.relative_to(root_dir)
                for i in range(len(rel_parent.parts)):
                    dir_path = Path(*rel_parent.parts[:i + 1])
                    dir_str = str(dir_path)
                    if dir_str not in dirs_created:
                        dirs_created.append(dir_str)

            # Calculate relative symlink path
            rel_symlink = os.path.relpath(src_path, dst_path.parent)

            # Create symlink
            dst_path.symlink_to(rel_symlink)
            encrypted_symlinks.append(dst)
            symlinks_created.append(dst)
            output.created(f"{dst} (decrypted)")

            # Update metadata with symlink destination
            metadata["symlink_dst"] = dst

    # Write state
    write_state(root_dir, {
        "symlinks": symlinks_created,
        "created_directories": dirs_created,
        "encrypted_files": encrypted_files,
    })

    # Update git exclude
    _update_git_exclude_safe(root_dir, symlinks_created)

    # Warn about symlinks tracked by main repo's git index
    if symlinks_created and (root_dir / ".git").exists():
        try:
            tracked = git.get_tracked_files(root_dir, symlinks_created)
            if tracked:
                output.warning(
                    f"{len(tracked)} overlay symlink(s) are tracked by the main repo's git index.\n"
                    "  Git operations (checkout, merge, pull) will silently replace these symlinks\n"
                    "  with regular files, breaking the overlay link.\n"
                    "  To fix, run:\n"
                    "    git rm --cached " + " ".join(tracked) + "\n"
                    "    git commit -m 'Untrack overlay-managed files'\n"
                    "  Consider also adding them to .gitignore to prevent future tracking."
                )
        except git.GitError:
            pass  # Ignore if git check fails

    # Inform about .git/info/exclude being local-only
    if symlinks_created:
        output.info(
            "Note: Overlay symlinks are excluded via .git/info/exclude (local only).\n"
            "  To protect collaborators, consider adding overlay paths to .gitignore."
        )

    output.success("Overlay cloned and symlinks created successfully.")


def sync_overlay(
    root_dir: Path,
    config: dict[str, Any],
    *,
    force: bool = False,
    dry_run: bool = False,
    output: Output | None = None,
) -> int:
    """Sync symlinks with current config.

    Args:
        root_dir: Root directory of main repo.
        config: Validated config dict.
        force: Overwrite existing destinations
        dry_run: Preview changes without making them
        output: Output handler

    Returns:
        Exit code (0 success, 2 partial/warnings)

    Raises:
        OverlayError: If operation fails.
    """
    if output is None:
        output = get_output()

    repo_dir = get_repo_dir(root_dir)
    decoded_dir = get_decoded_dir(root_dir)
    overlay_config = config["overlay"]
    exit_code = 0

    # Check if repo exists
    if not repo_dir.exists():
        raise OverlayError("Overlay repo not cloned. Run 'repoverlay clone' first")

    # Load state for encrypted files
    state = read_state(root_dir)
    encrypted_files = state.get("encrypted_files", {})

    # Scan for ALL encrypted files (to exclude from regular mappings)
    all_enc_files = sops.scan_encrypted_files(repo_dir)
    all_enc_file_strs = {str(f) for f in all_enc_files}
    new_enc_files = [f for f in all_enc_files if str(f) not in encrypted_files]

    # Handle new encrypted files (e.g., pulled from remote)
    if new_enc_files:
        sops_config = sops.get_sops_config_path(repo_dir, config)
        if not sops.is_sops_available():
            output.warning(
                f"Found {len(new_enc_files)} encrypted file(s) but SOPS is not installed.\n"
                "  Install SOPS to decrypt: brew install sops (macOS) or apt install sops (Linux)"
            )
            for f in new_enc_files:
                output.info(f"    - {f}")
            exit_code = 2
        else:
            # Try to decrypt new encrypted files
            for enc_path in new_enc_files:
                enc_path_str = str(enc_path)
                decoded_name = sops.get_decoded_path(enc_path_str)
                src = repo_dir / enc_path
                dst = decoded_dir / decoded_name

                try:
                    sops.decrypt_file(src, dst, sops_config)
                    encrypted_files[enc_path_str] = {
                        "decoded_path": decoded_name,
                        "symlink_dst": decoded_name,
                        "last_encrypted_hash": sops.file_hash(src),
                        "last_decoded_hash": sops.file_hash(dst),
                    }
                    output.info(f"Decrypted new file: {output.path(decoded_name)}")
                except sops.SopsDecryptionError as e:
                    output.warning(f"Cannot decrypt {enc_path}: {e}")
                    exit_code = 2
                except sops.SopsError as e:
                    output.warning(f"Failed to decrypt {enc_path}: {e}")
                    exit_code = 2

    # Re-decrypt existing files if encrypted sources changed
    if encrypted_files:
        sops_config = sops.get_sops_config_path(repo_dir, config)
        try:
            re_decrypted = sops.re_decrypt_if_changed(
                repo_dir, decoded_dir, encrypted_files, sops_config
            )
            if re_decrypted:
                output.info(f"Re-decrypted {len(re_decrypted)} updated file(s)")
        except sops.SopsError as e:
            output.warning(f"Failed to re-decrypt some files: {e}")
            exit_code = 2

    # Generate or use explicit mappings
    explicit_mappings = overlay_config.get("mappings")
    if explicit_mappings:
        mappings = explicit_mappings
        # Validate explicit mappings
        try:
            validate_mappings(mappings)
        except ValidationError as e:
            raise OverlayError(str(e))
    else:
        # Exclude all encrypted files from regular mappings (even if decryption failed)
        mappings = _generate_mappings_from_repo(repo_dir, encrypted_files, all_enc_file_strs)

    # Check repo URL mismatch (only for git repos)
    repo_url = overlay_config["repo"]
    if not _is_local_path(repo_url):
        try:
            actual_url = git.get_remote_url(repo_dir)
            if not _urls_match(actual_url, repo_url):
                output.warning(f"Repo URL mismatch: config has '{repo_url}', cloned repo has '{actual_url}'")
                exit_code = 2
        except git.GitError:
            pass  # Ignore if we can't get remote URL

    # Check for gitignore conflicts (informational)
    destinations = [m["dst"] for m in mappings]
    if check_gitignore_conflicts(root_dir, destinations, output):
        if exit_code == 0:
            exit_code = 2

    # Get old symlinks from already-loaded state
    old_symlinks = set(state.get("symlinks", []))

    # Load ignore patterns and filter mappings
    ignore_patterns = load_ignore_patterns(root_dir)
    mappings = filter_mappings(mappings, ignore_patterns)

    # Determine new symlinks (include both regular mappings and decoded file destinations)
    new_symlinks = {m["dst"] for m in mappings}
    for metadata in encrypted_files.values():
        symlink_dst = metadata.get("symlink_dst")
        if symlink_dst:
            new_symlinks.add(symlink_dst)

    # Find symlinks to remove (in old state but not in new config)
    to_remove = old_symlinks - new_symlinks

    # Find orphaned symlinks (target no longer exists)
    for dst in list(new_symlinks & old_symlinks):
        dst_path = root_dir / dst
        if dst_path.is_symlink() and not dst_path.exists():
            to_remove.add(dst)

    # Detect symlinks that have reverted to regular files
    reverted_symlinks = []
    for dst in list(new_symlinks & old_symlinks):
        dst_path = root_dir / dst
        if dst_path.exists() and not dst_path.is_symlink():
            reverted_symlinks.append(dst)

    if reverted_symlinks:
        output.warning(
            f"{len(reverted_symlinks)} symlink(s) have been replaced with regular files\n"
            "  (likely by a git checkout, merge, stash, or an editor that replaces symlinks):"
        )
        for dst in sorted(reverted_symlinks):
            output.info(f"    {dst}")
        if force:
            output.info("  Recreating symlinks (--force).")
        else:
            output.info(
                "  Use 'repoverlay sync --force' to recreate these symlinks.\n"
                "  WARNING: The regular file may contain edits not in the overlay repo.\n"
                "  Back up any changes before using --force.\n"
                "  To prevent this, run: git rm --cached <file> in the main repo."
            )
            exit_code = 2

    # Find symlinks to create
    to_create = []
    for mapping in mappings:
        dst = mapping["dst"]
        dst_path = root_dir / dst

        # Skip if already exists and is correct
        if dst_path.is_symlink():
            src_path = repo_dir / mapping["src"]
            expected_target = os.path.relpath(src_path, dst_path.parent)
            actual_target = os.readlink(dst_path)
            if actual_target == expected_target:
                continue

        to_create.append(mapping)

    if dry_run:
        for dst in to_remove:
            output.info(f"{output.dry_run_prefix()} Would remove symlink {output.path(dst)}")
        for mapping in to_create:
            output.info(f"{output.dry_run_prefix()} Would create symlink {output.path(mapping['dst'])}")
        return exit_code

    # Remove old symlinks
    for dst in to_remove:
        dst_path = root_dir / dst
        if dst_path.is_symlink():
            dst_path.unlink()
            output.removed(dst)

    # Create new symlinks
    symlinks_created, dirs_created, skipped = _create_symlinks(
        root_dir, repo_dir, to_create, output, force=force
    )

    # Create symlinks for decoded (encrypted) files that don't have symlinks yet
    for enc_path_str, metadata in encrypted_files.items():
        decoded_path = metadata.get("decoded_path")
        symlink_dst = metadata.get("symlink_dst", decoded_path)
        if not decoded_path:
            continue

        dst_path = root_dir / symlink_dst
        src_path = decoded_dir / decoded_path

        # Skip if symlink already exists and is correct
        if dst_path.is_symlink():
            expected_target = os.path.relpath(src_path, dst_path.parent)
            try:
                actual_target = os.readlink(dst_path)
                if actual_target == expected_target:
                    continue
            except OSError:
                pass

        # Skip if decoded file doesn't exist (decryption failed)
        if not src_path.exists():
            continue

        # Check if destination exists
        if dst_path.exists() or dst_path.is_symlink():
            if force:
                if dst_path.is_symlink():
                    dst_path.unlink()
                elif dst_path.is_file():
                    dst_path.unlink()
                else:
                    shutil.rmtree(dst_path)
            else:
                output.warning(f"Skipping {symlink_dst} - destination already exists (use --force to overwrite)")
                continue

        # Create parent directories if needed
        parent = dst_path.parent
        if not parent.exists():
            parent.mkdir(parents=True, exist_ok=True)
            rel_parent = parent.relative_to(root_dir)
            for i in range(len(rel_parent.parts)):
                dir_path = Path(*rel_parent.parts[:i + 1])
                dir_str = str(dir_path)
                if dir_str not in dirs_created:
                    dirs_created.append(dir_str)

        # Create symlink
        rel_symlink = os.path.relpath(src_path, dst_path.parent)
        dst_path.symlink_to(rel_symlink)
        symlinks_created.append(symlink_dst)
        output.created(f"{symlink_dst} (decrypted)")

    # Merge with existing symlinks that weren't removed
    all_symlinks = list((old_symlinks - to_remove) | set(symlinks_created))

    # Update state
    old_dirs = state.get("created_directories", [])
    all_dirs = list(set(old_dirs) | set(dirs_created))

    write_state(root_dir, {
        "symlinks": all_symlinks,
        "created_directories": all_dirs,
        "encrypted_files": encrypted_files,
    })

    # Update git exclude
    _update_git_exclude_safe(root_dir, all_symlinks)

    output.success("Sync complete.")
    return exit_code


def _create_symlinks(
    root_dir: Path,
    repo_dir: Path,
    mappings: list[dict],
    output: Output,
    *,
    force: bool = False,
) -> tuple[list[str], list[str], list[str]]:
    """Create symlinks for mappings.

    Args:
        root_dir: Root directory of main repo
        repo_dir: Path to cloned overlay repo
        mappings: List of mapping dicts
        output: Output handler
        force: Overwrite existing destinations

    Returns:
        Tuple of (symlinks_created, directories_created, skipped_files)

    Raises:
        OverlayError: If operation fails
    """
    symlinks_created = []
    dirs_created = []
    skipped = []

    for mapping in mappings:
        src = mapping["src"]
        dst = mapping["dst"]

        src_path = repo_dir / src
        dst_path = root_dir / dst

        # Verify source exists
        if not src_path.exists():
            raise OverlayError(f"Source not found in overlay: {src}")

        # Check destination
        if dst_path.exists() or dst_path.is_symlink():
            if force:
                if dst_path.is_symlink():
                    dst_path.unlink()
                elif dst_path.is_file():
                    dst_path.unlink()
                else:
                    import shutil
                    shutil.rmtree(dst_path)
            else:
                # Skip existing files with a warning instead of erroring
                output.warning(f"Skipping {dst} - destination already exists (use --force to overwrite)")
                skipped.append(dst)
                continue

        # Create parent directories if needed
        parent = dst_path.parent
        if not parent.exists():
            parent.mkdir(parents=True, exist_ok=True)
            # Track the directories we created
            rel_parent = parent.relative_to(root_dir)
            # Track all parent directories in the chain
            for i in range(len(rel_parent.parts)):
                dir_path = Path(*rel_parent.parts[:i + 1])
                dir_str = str(dir_path)
                if dir_str not in dirs_created:
                    dirs_created.append(dir_str)

        # Calculate relative symlink path
        rel_path = os.path.relpath(src_path, dst_path.parent)

        # Create symlink
        dst_path.symlink_to(rel_path)
        symlinks_created.append(dst)
        output.created(dst)

    return symlinks_created, dirs_created, skipped


def _urls_match(url1: str, url2: str) -> bool:
    """Check if two git URLs refer to the same repo.

    Normalizes URLs for comparison (handles git@ vs https://, trailing .git).

    Args:
        url1: First URL
        url2: Second URL

    Returns:
        True if URLs match
    """
    def normalize(url: str) -> str:
        url = url.strip()
        # Remove trailing .git
        if url.endswith(".git"):
            url = url[:-4]
        # Convert git@ to https://
        if url.startswith("git@"):
            # git@github.com:user/repo -> github.com/user/repo
            url = url[4:].replace(":", "/", 1)
        # Remove https:// prefix
        if url.startswith("https://"):
            url = url[8:]
        if url.startswith("http://"):
            url = url[7:]
        # Remove trailing slash
        url = url.rstrip("/")
        return url.lower()

    return normalize(url1) == normalize(url2)


class UncommittedChangesError(OverlayError):
    """Raised when there are uncommitted changes that would be lost."""

    def __init__(self, message: str, changed_files: list[str]):
        super().__init__(message)
        self.changed_files = changed_files


class UnpushedCommitsError(OverlayError):
    """Raised when there are unpushed commits that would be lost."""

    def __init__(self, message: str, commit_count: int):
        super().__init__(message)
        self.commit_count = commit_count


def unlink_overlay(
    root_dir: Path,
    *,
    remove_repo: bool = False,
    force: bool = False,
    dry_run: bool = False,
    output: Output | None = None,
) -> None:
    """Remove all symlinks and clean up.

    Args:
        root_dir: Root directory of main repo.
        remove_repo: Also remove .repoverlay/ directory
        force: Proceed even with uncommitted changes
        dry_run: Preview changes without making them
        output: Output handler

    Raises:
        UnpushedCommitsError: If there are unpushed commits (hard block)
        UncommittedChangesError: If there are uncommitted changes (unless force=True)
    """
    if output is None:
        output = get_output()

    from .exclude import remove_managed_section

    repo_dir = get_repo_dir(root_dir)

    # Pre-unlink validation (only if repo exists - handles resumable unlink case)
    if repo_dir.exists() and (repo_dir / ".git").exists():
        # Check for unpushed commits - hard block
        has_unpushed, commit_count = git.has_unpushed_commits(repo_dir)
        if has_unpushed:
            raise UnpushedCommitsError(
                f"Cannot unlink - there are {commit_count} unpushed commit(s) in the overlay repo.\n"
                "Run 'repoverlay push' first, or remove the commits with 'git reset'.",
                commit_count,
            )

        # Check for uncommitted changes - warn unless force
        has_uncommitted, changed_files = git.has_uncommitted_changes(repo_dir)
        if has_uncommitted and not force and not dry_run:
            raise UncommittedChangesError(
                "Uncommitted changes detected in overlay repo.",
                changed_files,
            )

    # Load state
    state = read_state(root_dir)
    symlinks = state.get("symlinks", [])
    created_dirs = state.get("created_directories", [])

    if dry_run:
        for symlink in symlinks:
            output.info(f"{output.dry_run_prefix()} Would remove symlink {output.path(symlink)}")
        for dir_path in sorted(created_dirs, key=len, reverse=True):
            output.info(f"{output.dry_run_prefix()} Would remove directory {output.path(dir_path)} (if empty)")
        if remove_repo:
            output.info(f"{output.dry_run_prefix()} Would remove {output.path('.repoverlay/')}")
        return

    # Remove symlinks
    for symlink in symlinks:
        symlink_path = root_dir / symlink
        if symlink_path.is_symlink():
            symlink_path.unlink()
            output.removed(symlink)

    # Remove created directories (only if empty, in reverse order by depth)
    for dir_path in sorted(created_dirs, key=len, reverse=True):
        full_path = root_dir / dir_path
        if full_path.is_dir():
            try:
                full_path.rmdir()  # Only removes if empty
                output.removed(dir_path + "/")
            except OSError:
                pass  # Directory not empty, skip

    # Update git exclude
    try:
        remove_managed_section(root_dir)
    except Exception:
        pass

    # Clear state
    write_state(root_dir, {"symlinks": [], "created_directories": []})

    if remove_repo:
        import shutil
        overlay_dir = get_overlay_dir(root_dir)
        if overlay_dir.exists():
            shutil.rmtree(overlay_dir)
            output.removed(".repoverlay/")

    output.success("Unlink complete.")


def verify_overlay(
    root_dir: Path,
    *,
    output: Output | None = None,
) -> list[dict]:
    """Verify all state-tracked symlinks are valid.

    Checks each symlink in state for:
    - Missing (symlink doesn't exist at all)
    - Reverted (regular file instead of symlink)
    - Broken (symlink exists but target doesn't)
    - Wrong target (symlink points to unexpected location)
    - Tracked by git (in main repo's index, will be overwritten)

    Args:
        root_dir: Root directory of main repo.
        output: Output handler.

    Returns:
        List of issue dicts with keys: path, issue, detail
    """
    if output is None:
        output = get_output()

    repo_dir = get_repo_dir(root_dir)
    decoded_dir = get_decoded_dir(root_dir)
    state = read_state(root_dir)
    symlinks = state.get("symlinks", [])
    encrypted_files = state.get("encrypted_files", {})

    if not symlinks:
        output.info("No symlinks in state to verify.")
        return []

    issues = []

    for dst in sorted(symlinks):
        dst_path = root_dir / dst

        if not dst_path.exists() and not dst_path.is_symlink():
            issues.append({"path": dst, "issue": "missing", "detail": "Symlink does not exist"})
            continue

        if dst_path.exists() and not dst_path.is_symlink():
            issues.append({
                "path": dst,
                "issue": "reverted",
                "detail": "Regular file instead of symlink (likely replaced by git or editor)",
            })
            continue

        if dst_path.is_symlink() and not dst_path.exists():
            target = os.readlink(dst_path)
            issues.append({
                "path": dst,
                "issue": "broken",
                "detail": f"Dangling symlink -> {target}",
            })
            continue

        # Symlink exists and target exists - check it points into .repoverlay/
        resolved = dst_path.resolve()
        try:
            resolved.relative_to(repo_dir.resolve())
            # Points into overlay repo - OK
        except ValueError:
            try:
                resolved.relative_to(decoded_dir.resolve())
                # Points into decoded dir - OK
            except ValueError:
                actual_target = os.readlink(dst_path)
                issues.append({
                    "path": dst,
                    "issue": "wrong_target",
                    "detail": f"Points to {actual_target}, expected target inside .repoverlay/",
                })
                continue

    # Check for git-tracked files
    if (root_dir / ".git").exists() and symlinks:
        try:
            tracked = git.get_tracked_files(root_dir, symlinks)
            for path in tracked:
                issues.append({
                    "path": path,
                    "issue": "tracked_by_git",
                    "detail": "File is in main repo's git index; git will replace symlink on checkout/merge",
                })
        except git.GitError:
            pass

    # Report results
    if issues:
        output.warning(f"Found {len(issues)} issue(s):")
        for issue in issues:
            label = issue["issue"].upper().replace("_", " ")
            output.info(f"  [{label}] {issue['path']}: {issue['detail']}")

        # Provide fix suggestions
        reverted = [i for i in issues if i["issue"] == "reverted"]
        tracked = [i for i in issues if i["issue"] == "tracked_by_git"]
        missing = [i for i in issues if i["issue"] == "missing"]
        broken = [i for i in issues if i["issue"] == "broken"]

        if reverted:
            output.info(
                "\nTo fix reverted symlinks: repoverlay sync --force\n"
                "  WARNING: Back up any edits in the regular files first."
            )
        if tracked:
            output.info(
                "\nTo fix tracked files: git rm --cached " + " ".join(i["path"] for i in tracked)
            )
        if missing or broken:
            output.info("\nTo fix missing/broken symlinks: repoverlay sync --force")
    else:
        output.success(f"All {len(symlinks)} symlink(s) verified OK.")

    return issues


def cloak_overlay(
    root_dir: Path,
    *,
    dry_run: bool = False,
    output: Output | None = None,
) -> None:
    """Cloak secrets: remove decrypted files and relink symlinks to encrypted files.

    For each tracked encrypted file:
    - Removes the decrypted file from .repoverlay/decoded/
    - Replaces the symlink (which currently points to the decoded file) with one
      that points directly to the encrypted file in .repoverlay/repo/ (WITHOUT the
      .enc suffix in the link name, so existing code paths still work).

    Args:
        root_dir: Root directory of main repo.
        dry_run: Preview changes without making them.
        output: Output handler.

    Raises:
        OverlayError: If operation fails.
    """
    if output is None:
        output = get_output()

    repo_dir = get_repo_dir(root_dir)
    decoded_dir = get_decoded_dir(root_dir)

    if not repo_dir.exists():
        raise OverlayError("Overlay repo not cloned. Run 'repoverlay clone' first")

    state = read_state(root_dir)
    encrypted_files = state.get("encrypted_files", {})

    if not encrypted_files:
        output.info("No encrypted files tracked - nothing to cloak.")
        return

    # Check for uncommitted changes in decloaked files before cloaking
    changed = sops.detect_decoded_changes(decoded_dir, repo_dir, encrypted_files)
    if changed:
        changed_names = [
            encrypted_files[e]["decoded_path"] for e in changed if "decoded_path" in encrypted_files[e]
        ]
        output.error(
            "Cannot cloak: the following decloaked file(s) have uncommitted changes:\n"
            + "".join(f"  - {name}\n" for name in changed_names)
            + "Run 'repoverlay commit' first to re-encrypt and commit changes."
        )
        raise OverlayError("Uncommitted changes in decloaked files. Commit changes before cloaking.")

    cloaked_count = 0
    already_cloaked = 0

    for enc_path_str, metadata in encrypted_files.items():
        decoded_path = metadata.get("decoded_path")
        symlink_dst = metadata.get("symlink_dst", decoded_path)

        if not decoded_path or not symlink_dst:
            continue

        if metadata.get("cloaked"):
            already_cloaked += 1
            continue

        enc_src = repo_dir / enc_path_str
        dst_path = root_dir / symlink_dst
        decoded_file = decoded_dir / decoded_path

        if not enc_src.exists():
            output.warning(f"Encrypted file not found: {enc_path_str}")
            continue

        if dry_run:
            output.info(
                f"{output.dry_run_prefix()} Would cloak {output.path(symlink_dst)}"
                f" (-> {enc_path_str})"
            )
            continue

        # Remove existing symlink (currently points to decoded file)
        if dst_path.is_symlink():
            dst_path.unlink()
        elif dst_path.exists():
            output.warning(f"Skipping {symlink_dst} - not a symlink, cannot cloak")
            continue

        # Remove decrypted file
        if decoded_file.exists():
            decoded_file.unlink()

        # Create symlink pointing directly to the encrypted file (link name has no .enc suffix)
        rel_symlink = os.path.relpath(enc_src, dst_path.parent)
        dst_path.symlink_to(rel_symlink)

        metadata["cloaked"] = True
        output.info(f"  ~ {output.path(symlink_dst)} -> {enc_path_str} (cloaked)")
        cloaked_count += 1

    if not dry_run:
        write_state(root_dir, state)
        if cloaked_count > 0:
            output.success(f"Cloaked {cloaked_count} file(s).")
        elif already_cloaked > 0:
            output.info("All files already cloaked.")
        else:
            output.info("Nothing to cloak.")


def decloak_overlay(
    root_dir: Path,
    config: dict[str, Any],
    *,
    file: str | None = None,
    dry_run: bool = False,
    output: Output | None = None,
) -> None:
    """Decloak secrets: decrypt files and restore symlinks to decrypted versions.

    Reverses cloak: for each tracked encrypted file (or a specific one):
    - Decrypts the encrypted file to .repoverlay/decoded/
    - Replaces the symlink (currently pointing to the .enc file) with one that
      points to the decrypted file in .repoverlay/decoded/.

    Args:
        root_dir: Root directory of main repo.
        config: Validated config dict.
        file: Optional file to decloak (decoded path, e.g. "secrets/config.yaml",
              or encrypted path, e.g. "secrets/config.yaml.enc").
        dry_run: Preview changes without making them.
        output: Output handler.

    Raises:
        OverlayError: If operation fails (SOPS unavailable, decryption error, etc.)
    """
    if output is None:
        output = get_output()

    repo_dir = get_repo_dir(root_dir)
    decoded_dir = get_decoded_dir(root_dir)

    if not repo_dir.exists():
        raise OverlayError("Overlay repo not cloned. Run 'repoverlay clone' first")

    state = read_state(root_dir)
    encrypted_files = state.get("encrypted_files", {})

    if not encrypted_files:
        output.info("No encrypted files tracked - nothing to decloak.")
        return

    sops_config = sops.get_sops_config_path(repo_dir, config)

    # Filter to a specific file if requested
    if file:
        targets: dict[str, dict] = {}
        for enc_path_str, metadata in encrypted_files.items():
            if (
                enc_path_str == file
                or metadata.get("decoded_path") == file
                or metadata.get("symlink_dst") == file
            ):
                targets[enc_path_str] = metadata
        if not targets:
            raise OverlayError(f"File not found in tracked encrypted files: {file}")
    else:
        targets = encrypted_files

    decloaked_count = 0
    already_decloaked = 0

    for enc_path_str, metadata in targets.items():
        decoded_path = metadata.get("decoded_path")
        symlink_dst = metadata.get("symlink_dst", decoded_path)

        if not decoded_path or not symlink_dst:
            continue

        if not metadata.get("cloaked", False):
            already_decloaked += 1
            continue

        enc_src = repo_dir / enc_path_str
        dst_path = root_dir / symlink_dst
        decoded_file = decoded_dir / decoded_path

        if not enc_src.exists():
            output.warning(f"Encrypted file not found: {enc_path_str}")
            continue

        if dry_run:
            output.info(
                f"{output.dry_run_prefix()} Would decloak {output.path(symlink_dst)}"
                f" (-> {decoded_path})"
            )
            continue

        # Decrypt file to decoded dir
        try:
            sops.decrypt_file(enc_src, decoded_file, sops_config)
        except sops.SopsNotAvailableError as e:
            raise OverlayError(str(e))
        except sops.SopsDecryptionError as e:
            raise OverlayError(str(e))

        # Remove existing symlink (currently points to the encrypted file)
        if dst_path.is_symlink():
            dst_path.unlink()
        elif dst_path.exists():
            output.warning(f"Skipping {symlink_dst} - not a symlink, cannot decloak")
            continue

        # Create symlink pointing to decrypted file
        rel_symlink = os.path.relpath(decoded_file, dst_path.parent)
        dst_path.symlink_to(rel_symlink)

        metadata["cloaked"] = False
        metadata["last_encrypted_hash"] = sops.file_hash(enc_src)
        metadata["last_decoded_hash"] = sops.file_hash(decoded_file)

        output.info(f"  ~ {output.path(symlink_dst)} -> {decoded_path} (decloaked)")
        decloaked_count += 1

    if not dry_run:
        write_state(root_dir, state)
        if decloaked_count > 0:
            output.success(f"Decloaked {decloaked_count} file(s).")
        elif already_decloaked > 0:
            output.info("All files already decloaked.")
        else:
            output.info("Nothing to decloak.")


def _update_git_exclude_safe(root_dir: Path, symlinks: list[str]) -> None:
    """Update git exclude file, ignoring errors.

    Args:
        root_dir: Root directory
        symlinks: List of symlinks
    """
    try:
        update_exclude_file(root_dir, symlinks)
    except Exception:
        pass  # Ignore errors updating exclude file


def _should_encrypt_at_destination(dst_rel: str, config: dict, encrypt_flag: bool) -> bool:
    """Determine if a file should be encrypted when moved into the overlay.

    Args:
        dst_rel: Destination relative path in the overlay repo.
        config: Validated config dict.
        encrypt_flag: Whether --encrypt flag was passed.

    Returns:
        True if the file should be encrypted.
    """
    if encrypt_flag:
        return True
    patterns = config.get("overlay", {}).get("encrypt_patterns", [])
    return bool(patterns and matches_any_pattern(dst_rel, patterns))


def _purge_history(repo_dir: Path, file_path: str, output: Output) -> None:
    """Rewrite repo history to remove a file using git-filter-repo.

    Args:
        repo_dir: Repository to rewrite.
        file_path: Repo-relative path to purge.
        output: Output handler.

    Raises:
        MigrateError: If git-filter-repo is missing or rewrite fails.
    """
    result = subprocess.run(
        ["git", "filter-repo", "--version"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise MigrateError(
            "git-filter-repo is not installed.\n"
            "Install it: pip install git-filter-repo  or  brew install git-filter-repo\n"
            "See https://github.com/newren/git-filter-repo"
        )

    result = subprocess.run(
        ["git", "filter-repo", "--path", file_path, "--invert-paths", "--force"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise MigrateError(f"History rewrite failed: {result.stderr.strip()}")


def migrate_file(
    root_dir: Path,
    config: dict,
    file_arg: str,
    destination: str | None,
    *,
    purge_history: bool,
    encrypt: bool,
    dry_run: bool,
    output: Output,
) -> None:
    """Move a file between the main repo and the overlay repo.

    Direction is detected automatically:
    - File inside root_dir (but not overlay) → main → overlay
    - File inside .repoverlay/repo/ → overlay → main

    Args:
        root_dir: Root directory of the main repo.
        config: Validated config dict.
        file_arg: Path to the file to migrate (relative to cwd or absolute).
        destination: Override destination path; defaults to same relative path.
        purge_history: If True, rewrite source repo history to remove the file.
        encrypt: If True, force encryption when moving into the overlay.
        dry_run: Preview only, no filesystem changes.
        output: Output handler.

    Raises:
        MigrateError: On any error condition.
    """
    # Phase 1 — Resolve source and detect direction
    abs_file = Path(file_arg)
    if not abs_file.is_absolute():
        abs_file = (Path.cwd() / abs_file).resolve()

    if not abs_file.exists() and not abs_file.is_symlink():
        raise MigrateError(f"File not found: {file_arg}")

    repo_dir = get_repo_dir(root_dir)
    decoded_dir = get_decoded_dir(root_dir)

    # Error if already a symlink into overlay
    if abs_file.is_symlink():
        link_target = Path(os.readlink(abs_file))
        if not link_target.is_absolute():
            link_target = (abs_file.parent / link_target).resolve()
        for overlay_base in (repo_dir, decoded_dir):
            try:
                link_target.relative_to(overlay_base)
                raise MigrateError(
                    f"File is already a symlink into the overlay: {file_arg}"
                )
            except ValueError:
                pass

    # Detect direction
    is_main_to_overlay = False
    is_overlay_to_main = False

    try:
        abs_file.relative_to(repo_dir)
        is_overlay_to_main = True
    except ValueError:
        pass

    if not is_overlay_to_main:
        try:
            abs_file.relative_to(root_dir)
            is_main_to_overlay = True
        except ValueError:
            pass

    if not is_main_to_overlay and not is_overlay_to_main:
        raise MigrateError(f"File is outside the project: {file_arg}")

    state = read_state(root_dir)
    sops_config = sops.get_sops_config_path(repo_dir, config)

    # Phase 2 — Determine destination path
    if is_main_to_overlay:
        rel_in_source = abs_file.relative_to(root_dir)
        dst_rel = Path(destination) if destination else rel_in_source
        should_encrypt = _should_encrypt_at_destination(str(dst_rel), config, encrypt)

        if should_encrypt:
            enc_dst_abs = repo_dir / (str(dst_rel) + ".enc")
            if enc_dst_abs.exists():
                raise MigrateError(
                    f"Encrypted destination already exists in overlay: {dst_rel}.enc"
                )
        else:
            dst_abs = repo_dir / dst_rel
            if dst_abs.exists():
                raise MigrateError(f"Destination already exists in overlay: {dst_rel}")

    else:  # overlay → main
        rel_in_source = abs_file.relative_to(repo_dir)
        dst_rel = Path(destination) if destination else rel_in_source
        # Strip encryption suffix from destination if present
        dst_rel_str = str(dst_rel)
        if sops.is_encrypted_file(dst_rel_str):
            dst_rel = Path(sops.get_decoded_path(dst_rel_str))
        dst_abs = root_dir / dst_rel

        if dst_abs.exists() or dst_abs.is_symlink():
            if dst_abs.is_symlink():
                existing_target = Path(os.readlink(dst_abs))
                if not existing_target.is_absolute():
                    existing_target = (dst_abs.parent / existing_target).resolve()
                if existing_target != abs_file.resolve():
                    raise MigrateError(f"Destination already exists: {dst_rel}")
            else:
                raise MigrateError(f"Destination already exists: {dst_rel}")

    # Phase 3 — Dry run
    if dry_run:
        if is_main_to_overlay:
            output.info(
                f"{output.dry_run_prefix()} Would move {output.path(str(rel_in_source))}"
                f" → overlay:{output.path(str(dst_rel))}"
            )
            if should_encrypt:
                output.info(
                    f"{output.dry_run_prefix()} Would encrypt → {str(dst_rel)}.enc"
                )
            output.info(
                f"{output.dry_run_prefix()} Would create symlink at"
                f" {output.path(str(rel_in_source))}"
            )
            output.info(
                f"{output.dry_run_prefix()} Would remove {output.path(str(rel_in_source))}"
                f" from main repo index (if tracked)"
            )
        else:
            output.info(
                f"{output.dry_run_prefix()} Would move overlay:{output.path(str(rel_in_source))}"
                f" → {output.path(str(dst_rel))}"
            )
            output.info(
                f"{output.dry_run_prefix()} Would remove symlink in main repo"
            )
            output.info(
                f"{output.dry_run_prefix()} Would remove {output.path(str(rel_in_source))}"
                f" from overlay index"
            )
        if purge_history:
            src_label = "main repo" if is_main_to_overlay else "overlay repo"
            output.info(
                f"{output.dry_run_prefix()} Would purge {str(rel_in_source)}"
                f" from {src_label} history"
            )
        return

    # Phase 4a — Execute: main → overlay
    if is_main_to_overlay:
        rel_in_source_str = str(rel_in_source)

        if should_encrypt:
            if not sops.is_sops_available():
                raise MigrateError(
                    "SOPS is not installed but encryption is required.\n"
                    "Install SOPS: brew install sops  or  apt install sops"
                )
            enc_dst_abs = repo_dir / (str(dst_rel) + ".enc")
            enc_dst_abs.parent.mkdir(parents=True, exist_ok=True)
            sops.encrypt_file(abs_file, enc_dst_abs, sops_config)
            # Also copy plaintext into decoded dir
            decoded_copy = decoded_dir / dst_rel
            decoded_copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(abs_file, decoded_copy)
            staged_path = str(dst_rel) + ".enc"
        else:
            dst_abs = repo_dir / dst_rel
            dst_abs.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(abs_file, dst_abs)
            staged_path = str(dst_rel)

        git.add(repo_dir, [staged_path])

        abs_file.unlink()

        # Create symlink at original location
        if should_encrypt:
            link_target = decoded_dir / dst_rel
        else:
            link_target = repo_dir / dst_rel
        abs_file.parent.mkdir(parents=True, exist_ok=True)
        rel_symlink = os.path.relpath(link_target, abs_file.parent)
        abs_file.symlink_to(rel_symlink)

        # Remove from main repo index if tracked
        tracked = git.get_tracked_files(root_dir, [rel_in_source_str])
        if tracked:
            git.rm(root_dir, tracked, cached=True)

        # Update state
        symlinks = state.get("symlinks", [])
        symlinks.append(rel_in_source_str)
        state["symlinks"] = symlinks
        if should_encrypt:
            state["encrypted_files"][staged_path] = {
                "decoded_path": str(dst_rel),
                "symlink_dst": rel_in_source_str,
                "last_encrypted_hash": sops.file_hash(enc_dst_abs),
                "last_decoded_hash": sops.file_hash(decoded_dir / dst_rel),
            }
        write_state(root_dir, state)
        _update_git_exclude_safe(root_dir, state["symlinks"])

        output.success(f"Migrated {rel_in_source_str} → overlay ({staged_path})")

        if purge_history:
            has_uncommitted, _ = git.has_uncommitted_changes(root_dir)
            if has_uncommitted:
                raise MigrateError(
                    "Cannot purge history: main repo has uncommitted changes. "
                    "Commit or stash them first."
                )
            _purge_history(root_dir, rel_in_source_str, output)
            output.warning("History rewritten. Force push: git push --force-with-lease")

    # Phase 4b — Execute: overlay → main
    else:
        rel_in_source_str = str(rel_in_source)
        dst_abs.parent.mkdir(parents=True, exist_ok=True)

        # Identify all symlinks in the main repo pointing to this overlay file
        # (do this BEFORE removing any symlinks, so we can find them)
        abs_file_resolved = abs_file.resolve()
        symlinks_to_remove = []
        for path_str in list(state.get("symlinks", [])):
            link = root_dir / path_str
            if link.is_symlink():
                lt = Path(os.readlink(link))
                if not lt.is_absolute():
                    lt = (link.parent / lt).resolve()
                if lt == abs_file_resolved:
                    symlinks_to_remove.append(path_str)

        # Remove any existing symlink at dst_abs before copying
        if dst_abs.is_symlink():
            dst_abs.unlink()

        if sops.is_encrypted_file(abs_file):
            if sops.is_sops_available():
                sops.decrypt_file(abs_file, dst_abs, sops_config)
            else:
                shutil.copy2(abs_file, dst_abs)
        else:
            shutil.copy2(abs_file, dst_abs)

        # Remove from overlay index (or delete directly if not tracked)
        try:
            git.rm(repo_dir, [rel_in_source_str])
        except git.GitError:
            abs_file.unlink(missing_ok=True)

        # Remove symlinks and update state
        for path_str in symlinks_to_remove:
            link = root_dir / path_str
            if link.is_symlink():
                link.unlink()
            state["symlinks"].remove(path_str)

        # Remove from encrypted_files state
        state["encrypted_files"].pop(rel_in_source_str, None)
        state["encrypted_files"].pop(rel_in_source_str + ".enc", None)
        if rel_in_source_str.endswith(".enc"):
            state["encrypted_files"].pop(rel_in_source_str[:-4], None)

        # Remove decoded copy if it exists
        decoded_name = sops.get_decoded_path(rel_in_source_str)
        decoded_copy = decoded_dir / decoded_name
        if decoded_copy.exists():
            decoded_copy.unlink()

        write_state(root_dir, state)
        _update_git_exclude_safe(root_dir, state["symlinks"])

        output.success(f"Promoted overlay:{rel_in_source_str} → {str(dst_rel)}")

        if purge_history:
            has_uncommitted, _ = git.has_uncommitted_changes(repo_dir)
            if has_uncommitted:
                raise MigrateError(
                    "Cannot purge history: overlay repo has uncommitted changes. "
                    "Commit or stash them first."
                )
            _purge_history(repo_dir, rel_in_source_str, output)
            output.warning(
                "Overlay history rewritten. Force push overlay: git push --force-with-lease"
            )
