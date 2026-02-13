# Security Policy

## Supported Versions

We provide security updates for the current minor release and the previous minor release. Patch releases may include security fixes.

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

## Reporting a Vulnerability

We take security seriously. If you believe you have found a security vulnerability, please report it responsibly.

**Do not** open a public GitHub issue for security vulnerabilities.

1. **Email** the maintainers with a description of the vulnerability, steps to reproduce, and any suggested fix. Prefer encrypted email if you have our keys.
2. **Include** your name/handle if you want to be credited in the advisory.
3. We will acknowledge receipt within a reasonable time and will work with you to confirm the issue and assess impact.
4. We will coordinate disclosure (e.g. patch release, CVE, advisory) and credit you unless you prefer to remain anonymous.

### What to expect

- We aim to triage and respond to valid reports promptly.
- We will keep you updated on remediation and disclosure timing.
- We support responsible disclosure: we prefer to release a fix before public disclosure when feasible.

### Scope

- Wave OS codebase, dependencies (within our control), and documented deployment configurations.
- Out of scope: vulnerabilities in third-party services (e.g. cloud providers, Vault, Kubernetes) unless they are specific to our usage or documentation.

## Security practices in this project

- **Dependency scanning:** `pip-audit` runs in CI; known vulnerable dependencies should be addressed before release.
- **SBOM:** Software Bill of Materials is generated and signed in CI/release (see [Release Process](docs/RELEASE_PROCESS.md)).
- **Secrets:** We do not commit secrets; use environment variables or a secrets manager (Vault, AWS, GCP). See [Secrets Rotation](docs/SECRETS_ROTATION.md) and [Deployment](docs/DEPLOYMENT.md).
- **Threat model:** See [Threat Model](docs/THREAT_MODEL.md) for assumptions and mitigations.
- **Access control:** RBAC and audit logging are documented in [Access Control](docs/ACCESS_CONTROL.md).
