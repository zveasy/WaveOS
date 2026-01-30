# Secrets Rotation

## Rotation Schedule
- **Restricted secrets** (tokens, signing keys, HMAC keys): rotate every 30–90 days.
- **Service credentials** (SMTP/SES, external APIs): rotate every 90 days or per provider policy.

## Rotation Steps
1. Create a new secret version in the provider (Vault/AWS/GCP).
2. Update the secret alias/name referenced by WaveOS.
3. Deploy the new secret to staging; run a validation pipeline.
4. Promote to production during a change window.
5. Revoke the previous secret version after validation.

## Verification Checklist
- Secrets are not logged (log redaction enabled).
- Bundle signing/verification succeeds with new HMAC key.
- Alerts and email integrations work after rotation.
