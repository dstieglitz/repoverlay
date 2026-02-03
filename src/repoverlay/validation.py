"""Path validation for repoverlay."""


class ValidationError(Exception):
    """Raised when path validation fails."""
    pass


def validate_path(path: str, is_dst: bool = False) -> None:
    """Validate a path for safety.

    Args:
        path: Path to validate
        is_dst: True if this is a destination path

    Raises:
        ValidationError: If path is invalid
    """
    # Check for .. segments
    parts = path.replace("\\", "/").split("/")
    if ".." in parts:
        raise ValidationError(f"Path cannot contain '..': {path}")

    if is_dst:
        # Destination must be relative
        if path.startswith("/"):
            raise ValidationError(f"Destination must be relative: {path}")

        # Destination cannot be in .git/
        if path == ".git" or path.startswith(".git/"):
            raise ValidationError(f"Destination cannot be in .git/: {path}")

        # Destination cannot overwrite repoverlay files
        if path == ".repoverlay" or path.startswith(".repoverlay/"):
            raise ValidationError(f"Cannot overwrite repoverlay files: {path}")

        if path == ".repoverlay.yaml":
            raise ValidationError(f"Cannot overwrite repoverlay files: {path}")

        if path == ".repoverlayignore":
            raise ValidationError(f"Cannot overwrite repoverlay files: {path}")


def validate_mappings(mappings: list[dict]) -> None:
    """Validate all mappings for path safety and conflicts.

    Args:
        mappings: List of mapping dicts with src/dst keys

    Raises:
        ValidationError: If any validation fails
    """
    destinations = []

    for mapping in mappings:
        src = mapping["src"]
        dst = mapping["dst"]

        # Validate individual paths
        validate_path(src, is_dst=False)
        validate_path(dst, is_dst=True)

        # Check for duplicate destinations
        if dst in destinations:
            raise ValidationError(f"Duplicate destination: {dst}")
        destinations.append(dst)

    # Check for overlapping paths
    _check_overlapping_paths(destinations)


def _check_overlapping_paths(paths: list[str]) -> None:
    """Check for overlapping paths where one is inside another.

    Args:
        paths: List of destination paths

    Raises:
        ValidationError: If overlapping paths found
    """
    # Sort by length to check shorter (potential parents) first
    sorted_paths = sorted(paths, key=len)

    for i, parent in enumerate(sorted_paths):
        parent_prefix = parent + "/"
        for child in sorted_paths[i + 1:]:
            if child.startswith(parent_prefix):
                raise ValidationError(
                    f"Overlapping paths: '{child}' inside '{parent}'"
                )
