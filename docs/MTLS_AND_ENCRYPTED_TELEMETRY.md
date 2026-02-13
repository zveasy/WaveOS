# mTLS and Encrypted Telemetry (DoD-Grade Ingestion)

WaveOS supports **mutual TLS (mTLS)** and **encrypted telemetry** for ingestion and command-and-control (C2) to meet DoD and zero-trust requirements.

## Overview

- **Telemetry ingestion:** Collectors can send data to a gateway or pipeline. For DoD, that path should use mTLS (client and server certificates) and optional payload encryption.
- **Bring your own gateway:** WaveOS does not implement the TLS stack itself; you configure **your gateway or proxy** (e.g. Envoy, nginx, or a dedicated ingestion service) with mTLS and point WaveOS at it.
- **Encryption at rest:** Run artifacts (run_meta, evidence) can be encrypted with `encrypt_artifacts=true` and `WAVEOS_ENCRYPTION_KEY` (Fernet); see [Secrets](SECRETS_ROTATION.md).

## Configuration (Gateway / Ingestion)

Use these settings to tell WaveOS where and how to reach an mTLS-protected ingestion endpoint. The **actual TLS handshake is performed by the gateway or HTTP client** you use; WaveOS uses these for optional client cert paths when making outbound requests (e.g. to an ingestion URL).

| Config / Env | Description |
|--------------|-------------|
| `ingestion_mtls_cert_path` / `WAVEOS_INGESTION_MTLS_CERT_PATH` | Path to client certificate (PEM) for mTLS to ingestion/C2. |
| `ingestion_mtls_key_path` / `WAVEOS_INGESTION_MTLS_KEY_PATH` | Path to client private key (PEM) for mTLS. |
| `ingestion_mtls_ca_path` / `WAVEOS_INGESTION_MTLS_CA_PATH` | Path to CA bundle (PEM) to verify server certificate. |
| `ingestion_url` / `WAVEOS_INGESTION_URL` | Optional ingestion endpoint URL (used by collectors if set). |

If these are not set, no client mTLS is applied; the gateway in front of WaveOS can still enforce mTLS for incoming connections.

## Bring Your Own Gateway (Recommended for DoD)

1. **Deploy a gateway** (e.g. Envoy, nginx, or a DoD-approved reverse proxy) in front of WaveOS or in front of the telemetry ingestion service.
2. **Configure the gateway** with:
   - Server certificate and key.
   - Client certificate verification (require client certs from WaveOS or from site devices).
   - TLS 1.2+ only; disable weak ciphers per STIG/DoD policy.
3. **Point WaveOS** (or devices) at the gateway URL. If WaveOS makes outbound calls to an ingestion API, set `ingestion_mtls_cert_path`, `ingestion_mtls_key_path`, and `ingestion_mtls_ca_path` so those requests use mTLS.
4. **Encrypted payloads:** For end-to-end confidentiality, encrypt telemetry payloads before send (e.g. with the same Fernet key used for artifacts, or a dedicated key). Document the key distribution and rotation process.

## Key Management

- Store certs and keys in a secure location (e.g. HSM, vault). Use env or secrets provider to pass paths or key material.
- Rotate certificates per your policy; see [SECRETS_ROTATION.md](SECRETS_ROTATION.md).
- Do not commit certificates or private keys to the repository.

## Compliance Notes

- **NIST 800-53 (SC-8, SC-13):** Protect transmitted information; use FIPS-approved cryptography for TLS and encryption.
- **STIG:** Align TLS version and cipher suite with applicable STIGs for your deployment.
