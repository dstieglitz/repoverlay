# SOPS Troubleshooting

## Decryption Failures

If decryption fails, repoverlay shows the SOPS error with a hint:

```
Warning: Cannot decrypt secrets.yaml.enc:
Failed to decrypt secrets.yaml.enc:
Error decrypting key: AccessDeniedException...
Hint: Are you using the correct credentials/profile?
```

## Common Issues

### Wrong AWS Profile

```bash
AWS_PROFILE=myprofile repoverlay sync
```

Or set a permanent default:

```bash
export AWS_PROFILE=myprofile
```

### Missing age Key

Ensure `SOPS_AGE_KEY_FILE` is set or the key is in the default location:

```bash
# Set explicitly
export SOPS_AGE_KEY_FILE=~/.config/sops/age/keys.txt

# Or place key at default location
~/.config/sops/age/keys.txt
```

### No Matching Creation Rules

If `sops encrypt` fails with "no matching creation rules", check that your `.sops.yaml` path patterns match the file you're encrypting:

```yaml
creation_rules:
  # This matches secrets/foo.enc but NOT secrets/foo.yaml.enc
  - path_regex: secrets/.*\.enc$
    age: age1xxx

  # This matches any .enc file at any depth
  - path_regex: .*\.enc$
    age: age1xxx
```

### SOPS Config Not Found

repoverlay searches for SOPS config in this order:

1. The path specified in `sops_config:` in `.repoverlay.yaml`
2. `.config/.sops.yaml` in the overlay repo
3. `.sops.yaml` in the overlay repo root

If none are found, SOPS encryption/decryption will fail. Check that the file exists in the overlay repo:

```bash
repoverlay list
ls .repoverlay/repo/.config/
ls .repoverlay/repo/
```

### SOPS Not Installed

```
Error: sops command not found
```

Install SOPS:

```bash
brew install sops        # macOS
apt install sops         # Debian/Ubuntu
```

Or download from [https://github.com/getsops/sops/releases](https://github.com/getsops/sops/releases).

## Testing Decryption Manually

You can test SOPS directly against a file in the overlay repo:

```bash
sops --config .repoverlay/repo/.config/.sops.yaml \
     --decrypt .repoverlay/repo/secrets.yaml.enc
```
