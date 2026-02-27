# `repoverlay sync`

Recreate symlinks after config changes or overlay updates.

```bash
repoverlay sync [--force] [--dry-run] [--intellij]
```

## When to Use

Run `sync` after:

- Modifying mappings in `.repoverlay.yaml`
- Pulling updates to the overlay repository with `git pull` (instead of `repoverlay pull`)
- Adding new files to the overlay repo directly
- Changing the `ref` in `.repoverlay.yaml`

## Flags

| Flag | Description |
|------|-------------|
| `--force`, `-f` | Overwrite existing destination files |
| `--dry-run`, `-n` | Preview changes without executing |
| `--intellij` | Configure IntelliJ IDEA to track overlay repo as VCS root |

## Behavior

`sync` reads the current `.repoverlay.yaml` and ensures all symlinks are in place. It does **not** re-clone the overlay repo — it only updates symlinks based on the current state of `.repoverlay/repo/`.

Files that already exist in your project are skipped with a warning. Use `--force` to overwrite them.

## Example

After adding a new mapping to `.repoverlay.yaml`:

```yaml
mappings:
  - src: terraform.tfvars
    dst: terraform/terraform.tfvars
  - src: new-service/config.yaml        # newly added
    dst: services/new-service/config.yaml
```

Run sync to create the new symlink:

```bash
repoverlay sync
```
