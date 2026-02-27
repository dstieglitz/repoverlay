# IntelliJ IDEA Integration

When working in IntelliJ IDEA (or other JetBrains IDEs), symlinked files from the overlay won't show version control status by default because they live in a different git repository. Use the `--intellij` flag to register the overlay as an additional VCS root.

## Setup

```bash
repoverlay clone --intellij
```

This updates `.idea/vcs.xml` to include `.repoverlay/repo` as a git root, allowing IntelliJ to:

- Show git status for symlinked overlay files
- Track changes, diffs, and history for configuration files
- Commit overlay changes directly from the IDE

## Requirements

This only works if your project has a `.idea/` directory (i.e., has been opened in IntelliJ at least once).

## Using `--intellij` with Sync

The flag is also available on `sync`:

```bash
repoverlay sync --intellij
```

Use this if you forgot to pass `--intellij` on `clone`, or if the VCS root was removed.

## Cleanup

When you run `repoverlay unlink --remove-repo`, the VCS root is automatically removed from IntelliJ's configuration — no manual cleanup needed.
