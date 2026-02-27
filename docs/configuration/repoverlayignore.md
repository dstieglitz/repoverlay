# `.repoverlayignore`

The optional `.repoverlayignore` file lets you exclude files in the overlay repository from symlink creation. Place it in the root of your infrastructure project alongside `.repoverlay.yaml`.

## Example

```
# Ignore overlay's README
README.md

# Ignore all example files
*.example

# Ignore test directories
**/test/**

# Ignore CI configuration
.github/
```

## Pattern Syntax

| Pattern | Behavior |
|---------|----------|
| `*.example` | Any file ending in `.example` in the root |
| `README.md` | Exactly `README.md` in the root |
| `**/test/**` | Any file inside a `test/` directory at any depth |
| `config/` | The entire `config/` directory |

- `*` matches any characters except `/`
- `**` matches any characters including `/` (across directories)
- `?` matches a single character
- `[seq]` matches any character in the sequence
- Lines starting with `#` are comments
- Blank lines are ignored

## When to Use `.repoverlayignore`

Use `.repoverlayignore` when you want to **proactively** exclude files, rather than waiting for a conflict warning. Common candidates:

- `README.md` — your project has its own readme
- `LICENSE` — your project uses a different license
- `.github/` — CI workflows that don't apply to the main repo
- `**/test/**` — test fixtures that aren't needed in the main repo

!!! tip "Conflict handling"
    If an overlay file conflicts with an existing file in your project, repoverlay already skips it with a warning. `.repoverlayignore` is for cases where you want clean output without the warning. See [Conflict Handling](../reference/conflict-handling.md) for details.
