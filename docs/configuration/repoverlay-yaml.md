# `.repoverlay.yaml`

The `.repoverlay.yaml` file lives in the root of your infrastructure repository and tells repoverlay where the overlay repo lives and how files should be mapped.

## Full Example

```yaml
version: 1
overlay:
  repo: git@github.com:yourorg/config-prod.git
  ref: main
  sops_config: .config/.sops.yaml
  encrypt_patterns:
    - "secrets/**"
    - "**/*.secret.yaml"
    - "**/*.env"
  mappings:
    - src: terraform.tfvars
      dst: terraform/terraform.tfvars
    - src: ansible/inventory
      dst: ansible/inventory
    - src: helm/values.yaml
      dst: helm/values.yaml
```

## Field Reference

| Field | Required | Description |
|-------|----------|-------------|
| `version` | Yes | Must be `1` |
| `overlay.repo` | Yes | Git URL or local path of overlay repository |
| `overlay.ref` | No | Branch, tag, or commit to checkout |
| `overlay.mappings` | No | List of source/destination mappings. If omitted, all files in the overlay are symlinked using their original paths |
| `overlay.sops_config` | No | Path to `.sops.yaml` in overlay repo. Defaults to `.config/.sops.yaml` or `.sops.yaml` |
| `overlay.encrypt_patterns` | No | Glob patterns for auto-encrypting files on `repoverlay add` or `repoverlay import` |
| `mappings[].src` | Yes | Path in overlay repo |
| `mappings[].dst` | Yes | Path in main repo (must be relative) |

## Mappings

Mappings define how files in the overlay repo are placed in your project.

```yaml
mappings:
  - src: terraform.tfvars       # path inside overlay repo
    dst: terraform/terraform.tfvars  # path in your project
```

### Without Mappings

When `mappings` is omitted, repoverlay symlinks **all files** from the overlay repository into your project using the same relative paths:

```yaml
version: 1
overlay:
  repo: git@github.com:yourorg/config-prod.git
```

If the overlay repo contains `terraform/terraform.tfvars` and `ansible/inventory`, symlinks will be created at those exact paths in your project.

## Local Repositories

The `repo` field accepts local filesystem paths as well as remote URLs:

```yaml
version: 1
overlay:
  repo: ../config-local          # relative path
  # or
  repo: /path/to/config-dir      # absolute path
```

- If the path is a git repository, it will be cloned (preserving git history)
- If the path is a plain directory, it will be copied
- For plain directories, `ref` is ignored

See [Local Directory Overlay](../examples/local-overlay.md) for a full example.

## Path Validation

Destination paths in `mappings` are validated:

- Must be relative (no leading `/`)
- Cannot contain `..`
- Cannot be in `.git/`
- Cannot overwrite `.repoverlay.yaml`, `.repoverlayignore`, or `.repoverlay/`
- Cannot have duplicates
- Cannot overlap (e.g., `config` and `config/secrets`)
