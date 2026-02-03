"""Tests for IntelliJ IDEA integration."""

import io
import xml.etree.ElementTree as ET

import pytest

from repoverlay.intellij import configure_vcs_root, remove_vcs_root
from repoverlay.output import Output


@pytest.fixture
def output():
    """Create a fresh Output instance for tests."""
    return Output(quiet=True)


def test_configure_vcs_root_no_idea_dir(tmp_path, output):
    """Should skip if .idea/ doesn't exist."""
    result = configure_vcs_root(tmp_path, output=output)
    assert result is False


def test_configure_vcs_root_creates_vcs_xml(tmp_path, output):
    """Should create vcs.xml if it doesn't exist."""
    idea_dir = tmp_path / ".idea"
    idea_dir.mkdir()

    result = configure_vcs_root(tmp_path, output=output)

    assert result is True
    vcs_file = idea_dir / "vcs.xml"
    assert vcs_file.exists()

    # Parse and verify content
    tree = ET.parse(vcs_file)
    root = tree.getroot()
    component = root.find(".//component[@name='VcsDirectoryMappings']")
    assert component is not None

    mappings = component.findall("mapping")
    directories = [m.get("directory") for m in mappings]
    assert "$PROJECT_DIR$" in directories
    assert "$PROJECT_DIR$/.repoverlay/repo" in directories


def test_configure_vcs_root_updates_existing(tmp_path, output):
    """Should add mapping to existing vcs.xml."""
    idea_dir = tmp_path / ".idea"
    idea_dir.mkdir()

    # Create existing vcs.xml without overlay mapping
    vcs_file = idea_dir / "vcs.xml"
    vcs_file.write_text('''<?xml version="1.0" encoding="UTF-8"?>
<project version="4">
  <component name="VcsDirectoryMappings">
    <mapping directory="$PROJECT_DIR$" vcs="Git" />
  </component>
</project>
''')

    result = configure_vcs_root(tmp_path, output=output)

    assert result is True

    # Verify overlay mapping was added
    tree = ET.parse(vcs_file)
    root = tree.getroot()
    component = root.find(".//component[@name='VcsDirectoryMappings']")
    mappings = component.findall("mapping")
    directories = [m.get("directory") for m in mappings]
    assert "$PROJECT_DIR$/.repoverlay/repo" in directories
    assert len(mappings) == 2  # Original + overlay


def test_configure_vcs_root_idempotent(tmp_path, output):
    """Should not duplicate mapping if already present."""
    idea_dir = tmp_path / ".idea"
    idea_dir.mkdir()

    # Create vcs.xml with overlay mapping already present
    vcs_file = idea_dir / "vcs.xml"
    vcs_file.write_text('''<?xml version="1.0" encoding="UTF-8"?>
<project version="4">
  <component name="VcsDirectoryMappings">
    <mapping directory="$PROJECT_DIR$" vcs="Git" />
    <mapping directory="$PROJECT_DIR$/.repoverlay/repo" vcs="Git" />
  </component>
</project>
''')

    result = configure_vcs_root(tmp_path, output=output)

    assert result is True

    # Verify no duplicate
    tree = ET.parse(vcs_file)
    root = tree.getroot()
    component = root.find(".//component[@name='VcsDirectoryMappings']")
    mappings = component.findall("mapping")
    assert len(mappings) == 2


def test_configure_vcs_root_dry_run(tmp_path, output):
    """Should not modify files in dry run mode."""
    idea_dir = tmp_path / ".idea"
    idea_dir.mkdir()

    result = configure_vcs_root(tmp_path, dry_run=True, output=output)

    assert result is True
    vcs_file = idea_dir / "vcs.xml"
    assert not vcs_file.exists()


def test_remove_vcs_root(tmp_path, output):
    """Should remove overlay mapping from vcs.xml."""
    idea_dir = tmp_path / ".idea"
    idea_dir.mkdir()

    # Create vcs.xml with overlay mapping
    vcs_file = idea_dir / "vcs.xml"
    vcs_file.write_text('''<?xml version="1.0" encoding="UTF-8"?>
<project version="4">
  <component name="VcsDirectoryMappings">
    <mapping directory="$PROJECT_DIR$" vcs="Git" />
    <mapping directory="$PROJECT_DIR$/.repoverlay/repo" vcs="Git" />
  </component>
</project>
''')

    result = remove_vcs_root(tmp_path, output=output)

    assert result is True

    # Verify overlay mapping was removed
    tree = ET.parse(vcs_file)
    root = tree.getroot()
    component = root.find(".//component[@name='VcsDirectoryMappings']")
    mappings = component.findall("mapping")
    directories = [m.get("directory") for m in mappings]
    assert "$PROJECT_DIR$/.repoverlay/repo" not in directories
    assert "$PROJECT_DIR$" in directories
    assert len(mappings) == 1


def test_remove_vcs_root_no_file(tmp_path, output):
    """Should return False if vcs.xml doesn't exist."""
    result = remove_vcs_root(tmp_path, output=output)
    assert result is False


def test_remove_vcs_root_no_mapping(tmp_path, output):
    """Should return False if overlay mapping not present."""
    idea_dir = tmp_path / ".idea"
    idea_dir.mkdir()

    vcs_file = idea_dir / "vcs.xml"
    vcs_file.write_text('''<?xml version="1.0" encoding="UTF-8"?>
<project version="4">
  <component name="VcsDirectoryMappings">
    <mapping directory="$PROJECT_DIR$" vcs="Git" />
  </component>
</project>
''')

    result = remove_vcs_root(tmp_path, output=output)
    assert result is False
