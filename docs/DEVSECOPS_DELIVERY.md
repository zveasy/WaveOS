# DevSecOps Delivery Pipeline (No Physical Media)

This pipeline **replaces people bringing software disks in person**. New WaveOS builds are built, signed, and pushed to a registry or release so the external product (site running WaveOS) can receive updates without physical media.

## Overview

1. **Pipeline** (`.github/workflows/devsecops-delivery.yml`) runs on:
   - **Push tag `v*`** (e.g. `v1.2.0`): full delivery — test, build, sign, push image, create GitHub Release with distribution package.
   - **Manual run** (`workflow_dispatch`): same, with options to skip image push or release.

2. **Artifacts produced:**
   - Signed wheel and sdist (cosign keyless).
   - SBOM (Syft) and signatures.
   - Docker image pushed to **GitHub Container Registry** (`ghcr.io/<owner>/waveos:<version>`) and optionally to a **custom registry**.
   - **Distribution zip** (`waveos-<version>-distribution.zip`) containing wheel, SBOM, checksums, signatures, and `INSTALL.md`.

3. **External product** receives updates by either:
   - **Pulling the Docker image** from the registry (no disk).
   - **Downloading the distribution zip** from the GitHub Release (or S3, if configured), verifying signatures, and installing (pip or copy to cache for bundle install).

---

## Pipeline Steps

| Job | What it does |
|-----|----------------|
| **test-and-scan** | Lint, pytest, pip-audit. Must pass before build. |
| **build-and-sign** | Build wheel/sdist, generate SBOM, SHA256SUMS, cosign sign all artifacts. |
| **build-image** | Build Docker image; push to GHCR and optionally to custom registry. |
| **distribution-package** | Assemble zip with artifacts + INSTALL.md for site use. |
| **release** | Create GitHub Release (on tag) and attach dist + zip. |
| **s3-upload** | If secrets set, upload zip to S3 bucket for customer download. |

---

## Configuring the Pipeline

### Push to your own container registry

Add repository secrets:

- **REGISTRY_URL** — e.g. `registry.mycompany.com`
- **REGISTRY_USERNAME** — auth user
- **REGISTRY_PASSWORD** — auth token/password
- **REGISTRY_IMAGE** (optional) — image name (default `waveos`)

The workflow will push:

`<REGISTRY_URL>/<REGISTRY_IMAGE>:<version>`

So the site can pull with:

```bash
docker pull registry.mycompany.com/waveos:1.2.0
```

### Push distribution zip to S3

Add secrets:

- **AWS_ACCESS_KEY_ID**, **AWS_SECRET_ACCESS_KEY**
- **DELIVERY_S3_BUCKET** — bucket name
- **AWS_REGION** (optional, default `us-east-1`)

The zip is uploaded to:

`s3://<DELIVERY_S3_BUCKET>/waveos/waveos-<version>-distribution.zip`

Sites with access to the bucket (or a pre-signed URL / CloudFront) can download and install without GitHub access.

---

## How the External Product Receives Updates (No Disks)

### Option A: Pull Docker image from registry

1. Registry is reachable from the site (VPN, air-gapped mirror, or pull-through cache).
2. Site runs:
   ```bash
   docker pull ghcr.io/<owner>/waveos:1.2.0
   docker run --rm -e WAVEOS_LICENSE_KEY=... waveos:1.2.0 health-check
   ```
3. No physical media; repeat for new versions.

### Option B: Download distribution zip (e.g. from GitHub Release or S3)

1. Download `waveos-<version>-distribution.zip` from the [Releases](https://github.com/<owner>/<repo>/releases) page or from S3.
2. Transfer to the site via secure channel (not a USB stick if you can avoid it: e.g. secure file copy, approved download portal).
3. On the site, unzip and verify (see INSTALL.md in the zip):
   ```bash
   unzip waveos-1.2.0-distribution.zip
   cd waveos-1.2.0-distribution
   # Verify with cosign (identity matches workflow)
   cosign verify-blob --certificate-identity "https://github.com/<owner>/<repo>/.github/workflows/devsecops-delivery.yml@refs/tags/v1.2.0" \
     --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
     --signature waveos-1.2.0-*.whl.sig --certificate waveos-1.2.0-*.whl.crt waveos-1.2.0-*.whl
   pip install waveos-1.2.0-*.whl
   ```

### Option C: Air-gapped site (no direct internet to registry)

1. **Build and sign** in CI as usual; artifacts are in the release or S3.
2. **Transfer package** via approved air-gap process (e.g. one-way transfer, courier of signed media, or secure handoff from a connected staging network).
3. On the air-gapped side:
   - Copy the distribution zip (or wheel + SBOM + sigs) to the offline cache path.
   - Install: `pip install waveos-*.whl` (or use a local PyPI mirror), or for **application bundles** (policy/config): copy bundle dir to cache and run `waveos bundle install --from-cache <cache_dir> --bundle-id <id>`.

Using the **same signed artifacts** as the connected pipeline ensures no “sneakernet” of unsigned code; only the transfer step is physical or out-of-band.

### Air-gapped transfer process (DoD / classified)

1. **Build and sign** in CI as usual (tag or manual run). Artifacts are in the GitHub Release or S3.
2. **On a connected staging network:** Download the distribution zip (and optional bundle zip). Verify with cosign (see INSTALL.md). Optionally re-package onto **approved transfer media** (e.g. one-way transfer device, courier-approved drive) per your site's procedures.
3. **Transfer** via your approved process: one-way transfer, courier, or classified network handoff. Document the transfer (date, custodian, media ID) for chain of custody.
4. **On the air-gapped side:** Copy the zip(s) to the target system. Verify signatures again if the verification tooling is available offline (e.g. cosign with cached keys). Install per INSTALL.md. For bundles: copy to cache, then `waveos bundle install --from-cache <path> --bundle-id <id>` (set `WAVEOS_ENCRYPTION_KEY` if the bundle was built with `--encrypt`).
5. **Retain** transfer and install logs for audit. Run at least one full install and health-check on the air-gapped side and document in your deployment record.

### DoD distribution compliance (who can push what, where)

- **RBAC:** WaveOS uses roles (e.g. operator, viewer) and clearance-based actions (e.g. `DEPLOY_BUNDLE`, `MANAGE_NODES`). Restrict who can run `bundle install` and who can approve recovery.
- **Pipeline:** Restrict who can trigger the DevSecOps delivery workflow (tag push or manual run) and who can access registry/S3 secrets. Use branch protection and required reviews for release tags.
- **Registry / S3:** Use separate registries or buckets per classification or program if required. Document which registry or bucket is authorized for which environment.
- **Signing:** Cosign (keyless or key-based) ensures artifact integrity. Ensure verification is part of site install procedures and that only verified artifacts are installed.

---

## Application / policy bundles (what runs on WaveOS)

If the external product already has WaveOS and you only ship **policy/config/application** updates:

1. Build a **WaveOS bundle** (directory with `bundle.json`, artifacts, and `bundle.sig`):
   ```bash
   waveos bundle build --dir ./my-policy-bundle --policy-version p2 --bundle-id my-app-1.0 --sign
   ```
2. For **encrypted payloads (DoD):** build with `--encrypt` (requires `WAVEOS_ENCRYPTION_KEY`). The same key must be available at the site for install.
3. Put that directory (or a zip of it) into your delivery pipeline: e.g. add a job that zips the signed bundle and uploads it to the release or S3.
4. On the site, copy the bundle to the cache and install:
   ```bash
   waveos bundle install --from-cache /path/to/cache --bundle-id my-app-1.0
   # If bundle was built with --encrypt, set WAVEOS_ENCRYPTION_KEY so artifacts are decrypted on install.
   # Optional canary: --canary-percent 10 --canary-dir ./out/bundles/canary
   # then after validation: waveos bundle promote
   ```

The same DevSecOps pipeline can be extended to produce and attach this bundle zip alongside the WaveOS distribution zip.

---

## Security

- **No long-lived signing keys:** Cosign keyless (OIDC) with GitHub Actions.
- **Verification:** Sites should verify artifact signatures with cosign before install (see INSTALL.md in the zip).
- **SBOM:** Included for supply-chain and compliance; sign and verify the SBOM the same way as the wheel.
- **Secrets:** Registry and S3 credentials live in GitHub (or your CI) secrets; never in the repo or the distribution zip.

---

## Triggering a delivery

- **Release:** Tag with `v1.2.0` (no `-rc`) and push; the workflow runs and creates the release.
- **Manual:** Actions → DevSecOps Delivery → Run workflow; optionally set version override and toggles for image push / release creation.

This gives you a single, repeatable way to push new builds to the external product without anyone bringing software disks on site.
