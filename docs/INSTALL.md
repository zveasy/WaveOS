# WaveOS: Install from distribution (no physical media)

This guide covers installing WaveOS from the **distribution zip** produced by the DevSecOps pipeline. The same content is included inside `waveos-<version>-distribution.zip` as `INSTALL.md` (with version and repo placeholders filled in).

See [DEVSECOPS_DELIVERY.md](DEVSECOPS_DELIVERY.md) for pipeline overview, registry/S3 options, and air-gapped install.

---

## 1. Get the distribution

- **From GitHub Release:** Download `waveos-<version>-distribution.zip` from the [Releases](https://github.com/OWNER/REPO/releases) page.
- **From S3:** If configured, download from `s3://<bucket>/waveos/waveos-<version>-distribution.zip` (or use the provided URL).

Replace `OWNER/REPO` with your GitHub org/repo and `<version>` with the release version (e.g. `1.2.0`).

---

## 2. Verify signatures (recommended)

Use [cosign](https://docs.sigstore.dev/cosign/overview/) to verify the wheel (and optionally the SBOM) before install.

**Wheel (tagged release):**

```bash
unzip waveos-<version>-distribution.zip
cd waveos-<version>-distribution

cosign verify-blob \
  --certificate-identity "https://github.com/OWNER/REPO/.github/workflows/devsecops-delivery.yml@refs/tags/v<version>" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  --signature waveos-<version>-*.whl.sig \
  --certificate waveos-<version>-*.whl.crt \
  waveos-<version>-*.whl
```

**Wheel (branch build / manual run):** Use `@refs/heads/main` (or the branch used) instead of `@refs/tags/v<version>` in `--certificate-identity`.

---

## 3. Install from wheel

```bash
pip install waveos-<version>-*.whl
```

Set license and config as needed (see [DEPLOYMENT.md](DEPLOYMENT.md), [PRODUCTION_CHECKLIST.md](PRODUCTION_CHECKLIST.md)):

```bash
export WAVEOS_LICENSE_KEY=WAVEOS-...   # or WAVEOS_LICENSE_PATH
waveos health-check
waveos -V
```

---

## 4. Or use Docker (pull from registry)

If the image is pushed to a registry (e.g. GHCR or your own):

```bash
docker pull ghcr.io/OWNER/waveos:<version>
docker run --rm -e WAVEOS_LICENSE_KEY=... ghcr.io/OWNER/waveos:<version> health-check
```

---

## 5. Air-gapped and bundles

- **Air-gapped:** Transfer the signed zip via your approved process; on the target host, verify with cosign (using cached keys if offline) and install per steps 2–3. See [DEVSECOPS_DELIVERY.md](DEVSECOPS_DELIVERY.md#option-c-air-gapped-site-no-direct-internet-to-registry).
- **Bundles:** For bundle install from cache: `waveos bundle install --from-cache <path> --bundle-id <id>`. Set `WAVEOS_ENCRYPTION_KEY` if the bundle was built with `--encrypt`.
