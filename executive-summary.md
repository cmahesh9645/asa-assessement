# Executive security summary

VulnTracker started as an internal prototype with weaknesses that could expose customer vulnerability records, allow users to see data belonging to others, and reveal credentials or internal error details. The most important application-level access and information-disclosure issues have now been addressed, and report sharing has been added with expiring, optionally password-protected links. The solution is materially safer, but it is not yet approved for unrestricted production use because deployment and dependency verification still need to be completed.

## Before and after

Before this work, search input could alter database queries, scan records were not consistently restricted to their owners, unsigned authentication tokens were permitted by configuration, passwords appeared in logs, and error responses exposed internal details. The application also trusted every browser origin for credentialed cross-origin requests.

After this work, database search uses bound parameters, scan reads and share creation enforce ownership, JWT verification accepts only the configured signing algorithm, sensitive login values are no longer logged, and clients receive generic server errors. Shared reports use unpredictable links that expire after one day; owners can add a password. The container runs as a non-root user, and the Kubernetes chart includes restricted ingress, resource limits, and secret retrieval from Azure Key Vault through External Secrets.

## Top three remaining risks

1. **A shared link can still be forwarded.** Anyone who obtains an unprotected link can read its report until it expires. The link is intentionally designed for external access. Short expiry and optional passwords reduce, but do not eliminate, this risk.
2. **The password is sent in the URL.** The requested API contract places the password in a query parameter. URLs can appear in browser history and infrastructure logs. HTTPS and query-string redaction are required; changing the API contract to accept the password in a request body is recommended.
3. **Production dependency and data-platform assurance is incomplete.** This offline environment could not run the security scanners or execute the test suite after dependency installation failed. The starter uses SQLite and automatic table creation, which are not a suitable long-term multi-replica database/migration strategy. CI scan results, a managed database, migrations, backup/restore tests, and operational validation are required before launch.

## Recommended next steps

- Run the CI pipeline and review all four JSON security reports; remediate critical and high findings before release.
- Deploy only with a unique signing key and database credentials in Azure Key Vault; verify the External Secrets integration and secret rotation.
- Move to a managed database, add schema migrations, enforce encryption and backups, and test restoration.
- Add share-link revocation, audit logging, rate limits, and a request-body password flow in the next API version.
- Validate TLS, ingress restrictions, network policies, monitoring, and incident-response procedures in a staging cluster.
