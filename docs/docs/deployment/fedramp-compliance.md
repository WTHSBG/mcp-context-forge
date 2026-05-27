# FedRAMP / FIPS Compliance Deployment

ContextForge supports opt-in FedRAMP compliance via UBI 9 base images and FIPS 140-2 hardening.
All compliance behavior is **disabled by default** — existing UBI 10 builds are unaffected.

## Findings Addressed

| Finding | Category | Control |
|---------|----------|---------|
| 1, 2, 3 | FIPS crypto policy | `update-crypto-policies --set FIPS` at build time |
| 7 | Root init-file permissions | `.bash_profile`, `.bashrc`, `.bash_logout` set to `0740` |
| 8 | rootfiles tmpfiles.d | `/etc/tmpfiles.d/rootfiles.conf` with `bash_profile` entry |
| 9 | SSH RekeyLimit | `/etc/ssh/ssh_config.d/02-rekey-limit.conf` → `512M 1h` |

## Build Requirements

- **Base images**: UBI 9 is mandatory for FIPS builds. UBI 10 (default) does not ship `crypto-policies-scripts`.
- **Python version**: Set `PYTHON_VERSION=3.11` — UBI 9 AppStream ships Python 3.11, not 3.12.
- **Build args required** when `ENABLE_FIPS=true`:

| Arg | Required UBI 9 value |
|-----|---------------------|
| `UBI_BASE` | `registry.access.redhat.com/ubi9/ubi@sha256:...` |
| `NODEJS_IMAGE` | `registry.access.redhat.com/ubi9/nodejs-20@sha256:...` |
| `UBI_MINIMAL` | `registry.access.redhat.com/ubi9/ubi-minimal@sha256:...` |

The runtime stage validates this at build time — if `ENABLE_FIPS=true` and `UBI_MINIMAL` does not
contain `ubi9`, the build aborts with an error message.

## Standard Build (No Change)

```bash
docker build -f Containerfile.lite .
```

Uses UBI 10 defaults. No compliance hardening applied.

## FedRAMP Build

```bash
make container-build-fips
```

Or manually:

```bash
docker build -f Containerfile.lite \
  --build-arg ENABLE_FIPS=true \
  --build-arg PYTHON_VERSION=3.11 \
  --build-arg UBI_BASE=registry.access.redhat.com/ubi9/ubi@sha256:c342e86b66854269554d8ac8e53e6e34d540c2289b06e19897037cb219c5ec59 \
  --build-arg NODEJS_IMAGE=registry.access.redhat.com/ubi9/nodejs-20@sha256:e395d430f6534e9f8df4519cbbf11fe5a3ac8f2c1209c821bf7b05520dd7c7ce \
  --build-arg UBI_MINIMAL=registry.access.redhat.com/ubi9/ubi-minimal@sha256:6ea809bdd8164f8b2b607e38f01b14c374a15bdfbc74fcd0155161512dd4e00e \
  --tag myimage:fedramp .
```

### Dreadnought / Internal Registry Override

Replace the public registry prefix with your internal mirror:

```bash
docker build -f Containerfile.lite \
  --build-arg ENABLE_FIPS=true \
  --build-arg PYTHON_VERSION=3.11 \
  --build-arg UBI_BASE=<internal-registry>/ubi9/ubi:latest \
  --build-arg NODEJS_IMAGE=<internal-registry>/ubi9/nodejs-20:latest \
  --build-arg UBI_MINIMAL=<internal-registry>/ubi9/ubi-minimal:latest \
  --tag myimage:fedramp .
```

Internal mirrors typically mirror by digest, so pinning is implicit.

## Post-Build Validation

Run `scripts/fedramp-validate.sh` inside the container to confirm all 7 compliance checks pass:

```bash
docker run --rm --entrypoint /bin/bash myimage:fedramp \
  -c "$(cat scripts/fedramp-validate.sh)"
```

Expected output:

```
=== FedRAMP Compliance Validation ===
  PASS: FIPS crypto policy set (findings 1/2/3)
  PASS: rootfiles tmpfile.d present (finding 8)
  PASS: rootfiles tmpfile.d contains bash_profile entry (finding 8)
  PASS: SSH RekeyLimit configured (finding 9)
  PASS: root .bash_profile permissions 0740 (finding 7)
  PASS: root .bashrc permissions 0740 (finding 7)
  PASS: root .bash_logout permissions 0740 (finding 7)

=== Results: 7 passed, 0 failed ===
```

Exit code 0 = compliant. Exit code 1 = at least one check failed.

## CI Verification

The `docker-scan.yml` workflow runs the FIPS build and validation gate on every push.
All three UBI 9 base images are pinned to SHA256 digests in CI for supply-chain integrity.
