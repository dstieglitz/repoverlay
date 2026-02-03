"""Git exclude file management for repoverlay."""

from pathlib import Path

BEGIN_MARKER = "# BEGIN repoverlay managed - do not edit"
END_MARKER = "# END repoverlay managed"


def get_exclude_path(root_dir: Path) -> Path:
    """Get path to .git/info/exclude file.

    Args:
        root_dir: Root directory of the repository

    Returns:
        Path to exclude file
    """
    return root_dir / ".git" / "info" / "exclude"


def update_exclude_file(root_dir: Path, symlinks: list[str]) -> None:
    """Update .git/info/exclude with managed section.

    Args:
        root_dir: Root directory of the repository
        symlinks: List of symlink paths to exclude
    """
    exclude_path = get_exclude_path(root_dir)

    # Ensure directory exists
    exclude_path.parent.mkdir(parents=True, exist_ok=True)

    # Read existing content
    existing_content = ""
    if exclude_path.exists():
        existing_content = exclude_path.read_text()

    # Remove existing managed section
    content_without_managed = _remove_managed_section(existing_content)

    # Build new managed section
    managed_section = _build_managed_section(symlinks)

    # Combine content
    new_content = content_without_managed.rstrip()
    if new_content:
        new_content += "\n\n"
    new_content += managed_section

    # Write back
    exclude_path.write_text(new_content)


def remove_managed_section(root_dir: Path) -> None:
    """Remove the managed section from .git/info/exclude.

    Args:
        root_dir: Root directory of the repository
    """
    exclude_path = get_exclude_path(root_dir)

    if not exclude_path.exists():
        return

    existing_content = exclude_path.read_text()
    new_content = _remove_managed_section(existing_content).rstrip()

    if new_content:
        new_content += "\n"

    exclude_path.write_text(new_content)


def _remove_managed_section(content: str) -> str:
    """Remove the managed section from content.

    Args:
        content: File content

    Returns:
        Content with managed section removed
    """
    lines = content.split("\n")
    result = []
    in_managed = False

    for line in lines:
        if line.strip() == BEGIN_MARKER:
            in_managed = True
            continue
        if line.strip() == END_MARKER:
            in_managed = False
            continue
        if not in_managed:
            result.append(line)

    return "\n".join(result)


def _build_managed_section(symlinks: list[str]) -> str:
    """Build the managed section content.

    Args:
        symlinks: List of symlink paths to exclude

    Returns:
        Managed section content
    """
    lines = [BEGIN_MARKER]

    # Always exclude repoverlay files
    lines.append(".repoverlay.yaml")
    lines.append(".repoverlayignore")
    lines.append(".repoverlay/")

    # Add symlinks
    for symlink in sorted(symlinks):
        lines.append(symlink)

    lines.append(END_MARKER)

    return "\n".join(lines) + "\n"
