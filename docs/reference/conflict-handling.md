# Conflict Handling

When a destination file already exists in your main repository (e.g., both repos have a `README.md`), repoverlay **skips** that file with a warning instead of failing:

```
Warning: Skipping README.md - destination already exists (use --force to overwrite)
```

## Behavior

- The conflicting file is **not** overwritten
- The file is **not** tracked in repoverlay's state
- `repoverlay unlink` and `repoverlay sync` will not affect it
- All other files in the overlay are processed normally

## Forcing Overwrites

Use `--force` to overwrite existing files:

```bash
repoverlay clone --force
repoverlay sync --force
```

## Proactive Exclusions

If you consistently want to skip certain overlay files without seeing the warning, add them to [`.repoverlayignore`](../configuration/repoverlayignore.md):

```
# Always skip these overlay files
README.md
LICENSE
.github/
```

## Common Scenarios

**Both repos have a `README.md`:**
Add `README.md` to `.repoverlayignore` to suppress the warning and keep your main repo's version.

**Overlay has `.env.example`, main repo has `.env`:**
These are different files (`src` and `dst` differ), so there's no conflict. But if both have the same destination path, add `*.example` to `.repoverlayignore`.

**You want the overlay version:**
Run `repoverlay sync --force` to overwrite the existing file with the overlay version.
