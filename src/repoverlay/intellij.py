"""IntelliJ IDEA integration for VCS root configuration."""

import xml.etree.ElementTree as ET
from pathlib import Path

from .output import Output, get_output


def configure_vcs_root(root_dir: Path, *, dry_run: bool = False, output: Output | None = None) -> bool:
    """Add .repoverlay/repo as a VCS root in IntelliJ IDEA.

    Updates .idea/vcs.xml to include the overlay repo as an additional
    git repository, allowing IntelliJ to track changes in symlinked files.

    Args:
        root_dir: Root directory of main repo (contains .idea/)
        dry_run: Preview changes without making them
        output: Output handler

    Returns:
        True if configuration was added/updated, False if skipped
    """
    if output is None:
        output = get_output()

    idea_dir = root_dir / ".idea"
    vcs_file = idea_dir / "vcs.xml"
    overlay_mapping = "$PROJECT_DIR$/.repoverlay/repo"

    # Check if .idea directory exists
    if not idea_dir.exists():
        output.info("No .idea/ directory found - skipping IntelliJ configuration")
        return False

    if dry_run:
        if vcs_file.exists():
            output.info(f"{output.dry_run_prefix()} Would update {output.path('.idea/vcs.xml')} with overlay VCS root")
        else:
            output.info(f"{output.dry_run_prefix()} Would create {output.path('.idea/vcs.xml')} with overlay VCS root")
        return True

    if vcs_file.exists():
        # Parse existing vcs.xml
        try:
            tree = ET.parse(vcs_file)
            root = tree.getroot()
        except ET.ParseError:
            output.warning("Could not parse .idea/vcs.xml - skipping IntelliJ configuration")
            return False

        # Find or create VcsDirectoryMappings component
        component = root.find(".//component[@name='VcsDirectoryMappings']")
        if component is None:
            component = ET.SubElement(root, "component", name="VcsDirectoryMappings")

        # Check if mapping already exists
        for mapping in component.findall("mapping"):
            if mapping.get("directory") == overlay_mapping:
                output.info("IntelliJ VCS root already configured")
                return True

        # Add the new mapping
        ET.SubElement(component, "mapping", directory=overlay_mapping, vcs="Git")

        # Write back with proper formatting
        _indent_xml(root)
        tree.write(vcs_file, encoding="UTF-8", xml_declaration=True)
    else:
        # Create new vcs.xml
        root = ET.Element("project", version="4")
        component = ET.SubElement(root, "component", name="VcsDirectoryMappings")
        ET.SubElement(component, "mapping", directory="$PROJECT_DIR$", vcs="Git")
        ET.SubElement(component, "mapping", directory=overlay_mapping, vcs="Git")

        _indent_xml(root)
        tree = ET.ElementTree(root)
        tree.write(vcs_file, encoding="UTF-8", xml_declaration=True)

    output.success("Added .repoverlay/repo as IntelliJ VCS root")
    return True


def remove_vcs_root(root_dir: Path, *, dry_run: bool = False, output: Output | None = None) -> bool:
    """Remove .repoverlay/repo VCS root from IntelliJ IDEA.

    Args:
        root_dir: Root directory of main repo
        dry_run: Preview changes without making them
        output: Output handler

    Returns:
        True if configuration was removed, False if not found
    """
    if output is None:
        output = get_output()

    vcs_file = root_dir / ".idea" / "vcs.xml"
    overlay_mapping = "$PROJECT_DIR$/.repoverlay/repo"

    if not vcs_file.exists():
        return False

    if dry_run:
        output.info(f"{output.dry_run_prefix()} Would remove overlay VCS root from {output.path('.idea/vcs.xml')}")
        return True

    try:
        tree = ET.parse(vcs_file)
        root = tree.getroot()
    except ET.ParseError:
        return False

    component = root.find(".//component[@name='VcsDirectoryMappings']")
    if component is None:
        return False

    # Find and remove the overlay mapping
    removed = False
    for mapping in component.findall("mapping"):
        if mapping.get("directory") == overlay_mapping:
            component.remove(mapping)
            removed = True
            break

    if removed:
        _indent_xml(root)
        tree.write(vcs_file, encoding="UTF-8", xml_declaration=True)
        output.info("Removed .repoverlay/repo from IntelliJ VCS roots")

    return removed


def _indent_xml(elem: ET.Element, level: int = 0) -> None:
    """Add indentation to XML elements for pretty printing.

    Args:
        elem: XML element to indent
        level: Current indentation level
    """
    indent = "\n" + "  " * level
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = indent + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = indent
        for child in elem:
            _indent_xml(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = indent
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = indent
