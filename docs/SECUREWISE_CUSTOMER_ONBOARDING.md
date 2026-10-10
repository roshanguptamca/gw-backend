# SecureWise customer onboarding

This guide describes the Phase 7 GitHub App code-scanning path that is present
in the branch. It does not describe a fully available customer URL assessment:
target registration, DNS/HTTPS ownership proof, and legal authorization are
still missing, and external DAST remains blocked.

## Operator setup (required before connecting a customer)

1. Back up the database, deploy the backend code, and apply the new migration
   with `python manage.py migrate`. Confirm the Django system check and worker
   readiness before enabling the UI flow. Do not deploy automatically from
   this branch.
2. Create a GitHub App for the SecureWise deployment. Grant repository
   metadata and contents read-only permissions only. Do not grant repository
   write permissions. Enable the installation and selected-repository lifecycle
   webhook events required to detect suspension/removal.
3. Configure the App Setup URL as
   `https://<api-host>/api/securewise/github-app/callback/`. Configure the
   webhook URL as `https://<api-host>/api/securewise/github-app/webhook/` and
   set a strong webhook secret.
4. Inject these values into the Django API and static-scanning worker
   environments through the deployment secret manager:

   ```text
   SECUREWISE_GITHUB_APP_ID=<numeric app id>
   SECUREWISE_GITHUB_APP_SLUG=<app slug>
   SECUREWISE_GITHUB_APP_PRIVATE_KEY=<PEM private key>
   SECUREWISE_GITHUB_APP_WEBHOOK_SECRET=<webhook secret>
   SECUREWISE_FRONTEND_URL=https://<frontend-host>
   ```

   The private key and webhook secret must not be committed, stored in an
   integration JSON field, or injected into customer scan containers. Do not
   configure the legacy GitHub personal-token integration as `github_app`.
5. Use the existing worker deployment guidance to configure a dedicated
   worker with scanner versions, constrained egress to GitHub API/codeload and
   required scanner update sources, resource limits and temporary disk
   capacity. Keep `SECUREWISE_RUNTIME_BUILDS_ENABLED` unset. A Docker socket
   remains host authority; this documentation is not proof of isolation.
6. Configure/verify Django session cookies and CSRF for the deployed frontend
   and API origins. GitHub returns to an authenticated setup callback; the
   initiating SecureWise organization admin must still be signed in.

For rollback, disable GitHub App setup and repository scans before reverting
the deployment. Restoring a database backup is preferred. Reversing the
SecureWise migration can remove installation/setup records and repository App
links, so only reverse it when that data and App-backed scan access can be
discarded.

## Customer code scan flow

1. Register/sign in and create an organization and project.
2. Open **Repositories**, choose the organization, and select **Connect
   GitHub App**. GitHub asks an authorized GitHub account owner to install the
   read-only App and select repositories.
3. After the signed-in admin returns, choose the connected GitHub account,
   load its installed repositories, select only the repositories to register,
   and optionally associate them with a project.
4. Create a Smart Scan for a selected repository and project, choose the
   desired static scan type, and start it. Repository source is retrieved as a
   pinned commit archive. The resulting scan records that commit SHA.
5. Review engine status, coverage, findings, remediation and the existing
   scan-level report. Scanner output is an automated observation and does not
   guarantee complete coverage or replace professional manual testing.

The App callback rejects installations with write permissions, consumes a
short-lived state once, and does not store installation access tokens.
Repository synchronization only accepts IDs returned by the selected
installation. A removed or suspended installation cannot be used for the next
archive download. Webhook delivery replay is suppressed.

## Not yet available

- Application URL ownership verification, explicit legal test authorization,
  scoped path exclusions, authorized URL scans and retests.
- Active URL testing, external ZAP, general authenticated website testing or
  automatic push/PR scans.
- Combined project reports spanning code and URL findings. Existing reports
  are scan-bound.
- A complete owner/admin/member/viewer invitation lifecycle. Existing
  membership roles and direct member administration remain in use.
- Customer retention settings, signed object-storage links, verified
  deletion/backup expiry, data-region selection or production tenant evidence.
- Verified dedicated Linux/rootless worker isolation, network egress policy or
  real GitHub App installation against a customer-owned private repository.

Do not scan a public/customer URL by bypassing the DAST guard, do not use
production credentials as synthetic accounts, and do not enable repository
runtime builds for customer code.
