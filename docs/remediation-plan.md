# Remediation plan and residual risk

## Completed in this change

1. Replaced SQL string interpolation with parameterized search and scoped results to the authenticated owner.
2. Enforced scan ownership on scan detail reads and share-link creation.
3. Removed JWT `none` algorithm acceptance.
4. Removed passwords from login logs and stopped returning stack traces to clients.
5. Removed arbitrary-origin credentialed CORS behavior.
6. Implemented share tokens as 256-bit random bearer secrets; only SHA-256 token hashes are stored. Links expire after 24 hours and optional passwords are bcrypt-hashed.
7. Added a non-root container and Kubernetes security controls.

## Residual risks and planned work

| Risk | Why not fully remediated | Residual risk | Effort | Compensating controls / next action |
|---|---|---|---|---|
| Password in share URL query string | The assignment explicitly requires `password` as a query parameter | Browser history, reverse-proxy logs, and analytics may retain it | 1–2 days | Enforce HTTPS, redact query strings from all logs, disable analytics on share route; change contract to POST body in a future API version |
| Share link is a bearer credential | External stakeholders need unauthenticated access | Anyone obtaining the link can access the report until expiry | 1 day | 24-hour expiry, high-entropy token, store only token hash, optional password; add revocation and audit events before production |
| Local-development secret fallback | Keeps the starter app runnable locally without setup | Unsafe if an operator deploys without injecting `SECRET_KEY` | 0.5 day | Helm ExternalSecret reads Azure Key Vault; deployment pipeline must validate secret presence and rotate credentials |
| SQLite default and schema lifecycle | Starter project has no migration framework or managed database setup | SQLite is unsuitable for multi-replica production and `create_all` is not a migration strategy | 2–4 days | Supply managed database URL through Key Vault; add Alembic migrations, backups, encryption, and restore testing |
| Dependency and image CVE status unverified in this offline run | Scanner binaries and network access were unavailable | Existing pinned dependencies may contain known vulnerabilities | 0.5–1 day | CI produces pip-audit and Trivy JSON; fail release on critical/high vulnerabilities and update pins based on scan evidence |

Do not treat a green unit-test run as proof of a clean security posture. Review the scanner artifacts and validate deployment settings in the target cluster.
