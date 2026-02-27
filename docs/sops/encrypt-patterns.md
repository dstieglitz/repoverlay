# Encrypt Patterns

`encrypt_patterns` is an optional list of glob patterns in `.repoverlay.yaml` that controls which files are automatically encrypted with SOPS when added to the overlay. Without this, you must pass `--encrypt` explicitly on every `repoverlay add` or `repoverlay import` call.

## Configuration

```yaml
version: 1
overlay:
  repo: git@github.com:yourorg/config-prod.git
  encrypt_patterns:
    - "secrets/**"
    - "**/*.secret.yaml"
    - "**/*.env"
    - "credentials.json"
```

## Pattern Syntax

| Pattern | Matches |
|---------|---------|
| `secrets/**` | All files anywhere under `secrets/` |
| `**/*.secret.yaml` | Any `.secret.yaml` file at any depth |
| `**/*.env` | Any `.env` file at any depth |
| `credentials.json` | Exactly `credentials.json` at the repo root |
| `config/db.*` | Any file named `db.*` directly inside `config/` |

- `*` matches any characters except `/`
- `**` matches across directory boundaries (any depth)
- `?` matches a single character
- Patterns are matched against the file's path relative to the overlay repo root

## Behavior

When `encrypt_patterns` is configured, any file whose path matches is encrypted automatically — no `--encrypt` flag needed:

```bash
# Without encrypt_patterns: must opt in
repoverlay add --encrypt secrets/database.yaml

# With encrypt_patterns: ["secrets/**"] — auto-encrypted
repoverlay add secrets/database.yaml

# Files that don't match are added as plaintext
repoverlay add terraform/terraform.tfvars
```

The same patterns apply to `repoverlay import`:

```bash
# Auto-encrypted because path matches "secrets/**"
repoverlay import secrets/database.yaml

# Plaintext because path doesn't match any pattern
repoverlay import ansible/inventory
```

## Example: Separating Secrets from Config

A common setup encrypts only sensitive files while keeping other config in plaintext:

```yaml
version: 1
overlay:
  repo: git@github.com:yourorg/config-prod.git
  encrypt_patterns:
    - "secrets/**"
    - "**/*.key"
    - "**/*.pem"
    - "vault-password"
```

With this config:

| File | Result |
|------|--------|
| `secrets/db-password.yaml` | Encrypted as `secrets/db-password.yaml.enc` |
| `ansible/inventory` | Added as plaintext |
| `tls/server.key` | Encrypted as `tls/server.key.enc` |
| `vault-password` | Encrypted as `vault-password.enc` |

Encrypted files appear in the overlay repo with a `.enc` suffix. When you clone or sync, they are automatically decrypted into `.repoverlay/decoded/` and symlinked as plaintext into your project.
