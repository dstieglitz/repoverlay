# SOPS Setup

## 1. Install SOPS

=== "macOS"
    ```bash
    brew install sops
    ```

=== "Debian/Ubuntu"
    ```bash
    apt install sops
    ```

=== "Binary"
    Download from the [SOPS releases page](https://github.com/getsops/sops/releases).

## 2. Add `.sops.yaml` to Your Overlay Repo

Create `.sops.yaml` (or `.config/.sops.yaml`) in your overlay repository. This file tells SOPS which encryption key to use for which files.

=== "AWS KMS"
    ```yaml
    creation_rules:
      - path_regex: .*\.enc$
        kms: arn:aws:kms:us-west-2:123456789012:key/your-key-id
    ```

=== "age"
    ```yaml
    creation_rules:
      - path_regex: .*\.enc$
        age: age1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
    ```

=== "PGP"
    ```yaml
    creation_rules:
      - path_regex: .*\.enc$
        pgp: YOUR_PGP_FINGERPRINT
    ```

=== "Multiple keys"
    ```yaml
    creation_rules:
      - path_regex: terraform/.*\.enc$
        kms: arn:aws:kms:us-west-2:123:key/terraform-key
      - path_regex: ansible/.*\.enc$
        age: age1xxxxxxxxx
      - path_regex: .*
        pgp: FINGERPRINT
    ```

## 3. Configure `.repoverlay.yaml`

Point repoverlay at your SOPS config (optional if it's at `.config/.sops.yaml` or `.sops.yaml`):

```yaml
version: 1
overlay:
  repo: git@github.com:yourorg/config-prod.git
  sops_config: .config/.sops.yaml    # optional custom path
  encrypt_patterns:
    - "secrets/**"
    - "**/*.secret.yaml"
```

## 4. Clone with Automatic Decryption

```bash
repoverlay clone
```

repoverlay finds the SOPS config, detects encrypted files (`.enc`, `.encoded`, `.encrypted`), and decrypts them automatically:

```
Found SOPS config: .config/.sops.yaml
Decrypting SOPS-encrypted files...
Decrypted 2 file(s)
  + secrets.yaml (decrypted)
  + ansible/vault-password (decrypted)
```

## SOPS Config Search Order

If `sops_config` is not set in `.repoverlay.yaml`, repoverlay searches for the SOPS config in this order:

1. `.config/.sops.yaml` in the overlay repo
2. `.sops.yaml` in the overlay repo root
