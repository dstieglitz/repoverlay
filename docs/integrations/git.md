# Git Integration

repoverlay automatically manages `.git/info/exclude` in your main repository to prevent accidental commits of overlay files and symlinks.

## Managed Exclude Entries

After `repoverlay clone`, your `.git/info/exclude` will contain a block like:

```
# BEGIN repoverlay managed - do not edit
.repoverlay.yaml
.repoverlayignore
.repoverlay/
config/secrets
.env
# END repoverlay managed - do not edit
```

This ensures that:

- The `.repoverlay/` working directory is never accidentally committed
- Symlinks created by repoverlay are excluded from the main repo's git index
- The repoverlay config files themselves are excluded

## How It Works

- When `repoverlay clone` or `repoverlay sync` runs, the managed block is written (or updated)
- When `repoverlay unlink` runs, the managed block is removed
- You should not edit the block manually; it is regenerated on each sync

## Overlay Repo Git Operations

All git operations for the overlay repo use repoverlay's passthrough commands (e.g., `repoverlay commit`, `repoverlay push`), which target `.repoverlay/repo/` rather than your main repo. See [Git Passthrough Commands](../commands/git-passthrough.md).
