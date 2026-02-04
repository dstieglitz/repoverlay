"""Overlay cloning and symlink creation."""

import os
import shutil
from pathlib import Path
from typing import Any

from . import git
from . import sops
from .exclude import update_exclude_file
from .ignore import filter_mappings, load_ignore_patterns
from .output import Output, get_output
from .state import read_state, write_state
from .validation import ValidationError, validate_mappings
from .warnings import check_gitignore_conflicts


class OverlayError(Exception):
    """Raised when overlay operations fail."""
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
    symlinks_created, dirs_created = _create_symlinks(root_dir, repo_dir, mappings, output, force=force)

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
                    raise OverlayError(f"Destination already exists: {dst_path}")

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
    symlinks_created, dirs_created = _create_symlinks(
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
                output.warning(f"Cannot create symlink, destination exists: {symlink_dst}")
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
) -> tuple[list[str], list[str]]:
    """Create symlinks for mappings.

    Args:
        root_dir: Root directory of main repo
        repo_dir: Path to cloned overlay repo
        mappings: List of mapping dicts
        output: Output handler
        force: Overwrite existing destinations

    Returns:
        Tuple of (symlinks_created, directories_created)

    Raises:
        OverlayError: If operation fails
    """
    symlinks_created = []
    dirs_created = []

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
                raise OverlayError(f"Destination already exists: {dst_path}")

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

    return symlinks_created, dirs_created


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
