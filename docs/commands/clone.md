# `repoverlay clone`

Clone the overlay repository and create symlinks.

```bash
repoverlay clone [URL] [--force] [--dry-run] [--intellij]
```

## Arguments & Flags

| Argument/Flag | Description |
|------|-------------|
| `URL` | Git URL or local path of overlay repo. Creates `.repoverlay.yaml` if none exists |
| `--force`, `-f` | Overwrite existing `.repoverlay/repo/` and destination files |
| `--dry-run`, `-n` | Preview changes without executing |
| `--intellij` | Configure IntelliJ IDEA to track overlay repo as VCS root |

## Cloning with a Config File

If `.repoverlay.yaml` already exists in your project, run:

```bash
repoverlay clone
```

repoverlay reads the config, clones the repo specified in `overlay.repo`, and creates symlinks according to `overlay.mappings` (or all files if no mappings are defined).

## Cloning without a Config File

If no `.repoverlay.yaml` exists, pass a URL directly and repoverlay creates one for you:

```bash
repoverlay clone git@github.com:yourorg/config-prod.git
```

This creates a minimal `.repoverlay.yaml`:

```yaml
version: 1
overlay:
  repo: git@github.com:yourorg/config-prod.git
```

All files from the overlay repo are then symlinked into your project at their original paths. You can edit `.repoverlay.yaml` afterward to add mappings or other options, then run `repoverlay sync` to apply the changes.

!!! note
    If a `.repoverlay.yaml` already exists, the URL argument is ignored and the existing config is used.

## Conflict Handling

Files that already exist in your project are skipped with a warning:

```
Warning: Skipping README.md - destination already exists (use --force to overwrite)
```

Use `--force` to overwrite existing files. See [Conflict Handling](../reference/conflict-handling.md) for more detail.

## Dry Run

Preview what would happen without making any changes:

```bash
repoverlay clone --dry-run
```

## IntelliJ Integration

Register the overlay repo as an additional VCS root in IntelliJ IDEA:

```bash
repoverlay clone --intellij
```

See [IntelliJ Integration](../integrations/intellij.md) for details.
