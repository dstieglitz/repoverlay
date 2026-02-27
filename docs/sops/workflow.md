# SOPS Workflow

## Basic Workflow

```bash
# Clone — encrypted files are decrypted automatically
repoverlay clone

# Edit the decrypted file directly
vim config/secrets.yaml

# Commit — changes are re-encrypted automatically
repoverlay commit -m "Update database password"

# Push encrypted files to remote
repoverlay push

# Pull — updated encrypted files are re-decrypted
repoverlay pull
```

## Adding Encrypted Files

### Option 1: Import from main repo (recommended)

```bash
repoverlay import --encrypt path/to/secrets.yaml
```

This encrypts the file, moves it to the overlay, removes it from the main repo's git index, and creates a symlink — all in one step.

### Option 2: Add an external file

```bash
repoverlay add --encrypt path/to/secrets.yaml
```

This will:

- Encrypt the file → `secrets.yaml.enc` in `.repoverlay/repo/`
- Copy plaintext to `.repoverlay/decoded/`
- Stage the encrypted file for commit

### Option 3: Configure auto-encryption patterns

```yaml
version: 1
overlay:
  repo: git@github.com:org/config.git
  encrypt_patterns:
    - "secrets/**"
    - "**/*.secret.yaml"
```

Files matching these patterns are automatically encrypted when added:

```bash
repoverlay add secrets/database.yaml  # auto-encrypted
```

## Multiple Keys

Different files can use different encryption keys. SOPS stores key metadata inside each encrypted file, so it automatically uses the correct key for decryption. Your `.sops.yaml` creation rules determine which key is used when *encrypting* new files:

```yaml
creation_rules:
  - path_regex: terraform/.*\.enc$
    kms: arn:aws:kms:us-west-2:123:key/terraform-key
  - path_regex: ansible/.*\.enc$
    age: age1xxxxxxxxx
  - path_regex: .*
    pgp: FINGERPRINT
```

## Cloaking and Decloaking

When stepping away from a machine or working on a shared screen, you may want to remove plaintext secrets from disk without losing the overlay structure:

```bash
# Remove plaintext from disk; symlinks now point to encrypted files
repoverlay cloak

# Restore plaintext; symlinks point back to .repoverlay/decoded/
repoverlay decloak

# Decloak just one file
repoverlay decloak secrets/database.yaml
```

See [cloak / decloak](../commands/cloak-decloak.md) for full details.
