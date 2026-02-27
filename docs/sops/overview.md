# SOPS Integration

repoverlay has built-in support for [SOPS](https://github.com/getsops/sops) encrypted files. Files ending in `.enc`, `.encoded`, or `.encrypted` are automatically detected, decrypted to a working directory, and symlinked as plaintext files. Changes are automatically re-encrypted on commit.

## How It Works

```
main-repo/
├── .repoverlay.yaml
├── .repoverlay/
│   ├── repo/                  # Cloned overlay (encrypted files)
│   │   ├── .config/
│   │   │   └── .sops.yaml     # SOPS configuration
│   │   └── secrets.yaml.enc   # Encrypted file
│   ├── decoded/               # Decrypted working copies
│   │   └── secrets.yaml       # Plaintext (git-ignored)
│   └── state.json
└── config/secrets.yaml -> ../.repoverlay/decoded/secrets.yaml
```

The workflow is transparent: your tools read plaintext files via symlinks, while only encrypted bytes are stored in the overlay repo.

## Key Operations

| Operation | What happens |
|-----------|-------------|
| `repoverlay clone` | Clones overlay, detects encrypted files, decrypts to `decoded/` |
| `repoverlay pull` | Pulls updates, re-decrypts any changed encrypted files, syncs symlinks |
| `repoverlay add --encrypt <file>` | Encrypts file → stores `.enc` in `repo/`, copies plaintext to `decoded/` |
| `repoverlay import --encrypt <file>` | Encrypts, moves from main repo to overlay, creates symlink |
| `repoverlay commit` | Re-encrypts any modified decrypted files before committing |
| `repoverlay cloak` | Removes plaintext from `decoded/`, symlinks point to `.enc` files |
| `repoverlay decloak` | Decrypts back to `decoded/`, restores symlinks to plaintext |

## Supported Key Types

SOPS supports multiple key management systems. repoverlay passes through to SOPS transparently, so any SOPS-supported key type works:

- **AWS KMS**
- **GCP KMS**
- **Azure Key Vault**
- **age**
- **PGP**

## Next Steps

- [Setup](setup.md) — install SOPS and configure your overlay
- [Encrypt Patterns](encrypt-patterns.md) — auto-encrypt files by path pattern
- [Workflow](workflow.md) — day-to-day SOPS workflow with repoverlay
- [Troubleshooting](troubleshooting.md) — common issues and fixes
