# WaveOS: Security Posture for Production / DoD-Industrial

For **production** and **DoD/industrial hardened** deployments, the following should be enforced or configured.

---

## A) Agent ↔ Coordinator

| Control | Description | Current / Required |
|--------|-------------|---------------------|
| **mTLS** | Coordinator TLS and client cert (agent identity). Set `WAVEOS_COORDINATOR_REQUIRE_MTLS=1` to require mTLS (reject requests without client cert). Set `WAVEOS_COORDINATOR_TLS=1` and cert/key for server TLS. | Configurable; require_mtls enforced when env set. |
| **AuthN** | Agent authentication: set `WAVEOS_COORDINATOR_AGENT_TOKEN`; agents send `Authorization: Bearer <token>`. For short-lived machine identity: use OIDC/JWT or cert-based (coordinator validates client cert in mTLS). | Bearer token supported; JWT/OIDC not yet implemented. |
| **Action signing** | Coordinator signs policy/actions; agent verifies before applying. | Implemented: waveos.action_signing; coordinator POST /actions/signed; agent uses WAVEOS_SIGNED_ACTIONS_PATH or WAVEOS_SIGNED_ACTIONS_JSON; evidence: action_signing_evidence.json. |

**Recommendation:** In production, enable coordinator TLS and agent token. Plan for mTLS client certs and action signing for DoD/industrial.

---

## B) Secrets

| Control | Description | Current / Required |
|--------|-------------|---------------------|
| **Secret provider required** | No env fallback in production. Set `WAVEOS_STRICT_SECRETS=1` or use config `strict_secrets: true`. With license (no `WAVEOS_LICENSE_SKIP`), `_json_fallback_allowed()` is false for Vault/AWS/GCP so `WAVEOS_*_SECRETS_JSON` is not used. | Enforced when not `LICENSE_SKIP`; strict_secrets further disables JSON fallback. |
| **Vault/AWS/GCP** | Use real provider (hvac, boto3, google-cloud-secret-manager). Tests that use JSON fallback run with `WAVEOS_LICENSE_SKIP=1` (dev mode). | Documented; integration tests require real credentials. |

**Recommendation:** In production, set `WAVEOS_LICENSE_SKIP=0` (or unset) and use a real secrets provider. Do not rely on `WAVEOS_*_SECRETS_JSON` in prod.

---

## C) Defaults to Harden

- **mTLS for coordinator:** Document that production deployments should set `WAVEOS_COORDINATOR_TLS=1` and supply cert/key.
- **Short-lived machine identity:** Use OIDC/JWT or cert-based; rotate tokens/certs. (Implementation: future.)
- **Action signing:** Implemented. Coordinator POST /actions/signed returns HMAC-SHA256 signed batch (actions + nonce + timestamp); agent verifies via WAVEOS_SIGNED_ACTIONS_PATH or WAVEOS_SIGNED_ACTIONS_JSON; evidence pack includes action_signing_evidence.json and verified_by_agent record.

---

## D) References

- [ACTUATOR_INTEGRATION_KIT.md](ACTUATOR_INTEGRATION_KIT.md) – Actuator safety and integration
- [MTLS_AND_ENCRYPTED_TELEMETRY.md](MTLS_AND_ENCRYPTED_TELEMETRY.md) – mTLS and encrypted telemetry
- [THREAT_MODEL.md](THREAT_MODEL.md) – Threat model and controls
