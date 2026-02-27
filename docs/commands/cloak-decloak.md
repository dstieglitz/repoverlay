# `repoverlay cloak` / `repoverlay decloak`

Cloak and decloak allow you to toggle SOPS-encrypted secrets between a plaintext and encrypted-only state on disk, without losing the overlay structure.

---

## `repoverlay cloak`

Remove all decrypted secret files from `.repoverlay/decoded/` and replace their symlinks with ones pointing directly to the encrypted files in `.repoverlay/repo/`. The symlink names remain unchanged (no `.enc` suffix), so existing tool paths continue to work—but the plaintext content is gone from disk.

```bash
repoverlay cloak [--dry-run]
```

| Flag | Description |
|------|-------------|
| `--dry-run`, `-n` | Preview changes without executing |

### Before and After

**Before cloaking:**
```
secrets.yaml -> .repoverlay/decoded/secrets.yaml   (plaintext on disk)
```

**After cloaking:**
```
secrets.yaml -> .repoverlay/repo/secrets.yaml.enc  (only encrypted bytes on disk)
```

### When to Use Cloak

- Stepping away from a machine
- Sharing your screen or doing a code review
- Checking in to a shared workstation
- Any time you want to ensure plaintext secrets are not present on disk without losing access to the overlay structure

---

## `repoverlay decloak`

Reverse `cloak`: decrypt encrypted files back to `.repoverlay/decoded/` and restore symlinks to point to the decrypted versions. Optionally decloak a single file.

```bash
repoverlay decloak [file] [--dry-run]
```

| Argument/Flag | Description |
|------|-------------|
| `file` | Specific file to decloak. Accepts the decoded name (`secrets.yaml`) or encrypted name (`secrets.yaml.enc`). Defaults to all tracked files |
| `--dry-run`, `-n` | Preview changes without executing |

### Examples

```bash
# Decloak everything
repoverlay decloak

# Decloak a single secret by its decoded name
repoverlay decloak secrets/database.yaml

# Decloak a single secret by its encrypted name
repoverlay decloak secrets/database.yaml.enc

# Preview what would happen
repoverlay decloak --dry-run
```

---

## Disk State Comparison

**Cloaked:**
```
main-repo/
├── .repoverlay/
│   ├── repo/
│   │   └── secrets.yaml.enc   ← encrypted content only
│   └── decoded/               ← empty (no plaintext)
└── secrets.yaml -> .repoverlay/repo/secrets.yaml.enc
```

**Decloaked:**
```
main-repo/
├── .repoverlay/
│   ├── repo/
│   │   └── secrets.yaml.enc
│   └── decoded/
│       └── secrets.yaml       ← plaintext here
└── secrets.yaml -> .repoverlay/decoded/secrets.yaml
```

The symlink name (`secrets.yaml`) is the same in both states. Tools that read the file continue to work in the decloaked state; in the cloaked state the symlink still exists but points to encrypted bytes.

---

## Notes

- Cloak/decloak state is tracked in `.repoverlay/state.json`
- Both operations are idempotent — running them twice is safe
- Requires SOPS to be installed and configured for decloaking
