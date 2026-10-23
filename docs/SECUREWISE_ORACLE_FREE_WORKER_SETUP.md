# Optional Oracle Cloud Always Free worker setup

Oracle Cloud is an optional place to host the generic Linux worker. There is
no Oracle SDK, queue, database, region, hostname or application branch in the
SecureWise worker. The identical provider-neutral worker can be moved to any
supported Linux VM provider by changing infrastructure and secrets only.

## Capacity and availability caveat

Oracle Always Free eligibility, Ampere A1 quotas, regional capacity and
account limits change over time and may be unavailable in a selected
tenancy/region. Check the current Oracle Cloud Free Tier page, service limits
and console quota/availability immediately before provisioning. Do not
assume a particular region or 2-OCPU/12-GB instance is available or remains
Always Free. Do not create billable resources without reviewing current
pricing and account billing settings.

**Quota checked 2026-10-11** against Oracle's
[Always Free resources documentation](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm):
it lists 1,500 Ampere A1 OCPU-hours and 9,000 GB-hours per month, equivalent
to 2 OCPUs and 12 GB RAM for an Always Free tenancy; allocation depends on
boot-volume size and total OCPUs. The page says the home region is required,
notes that temporary "out of host capacity" errors can occur, lists 200 GB
Always Free block volume and a 47 GB minimum boot volume per instance, and
warns idle instances may be reclaimed. These terms can change; recheck the
official page and console on the provisioning date.

## Provisioning checklist

1. Create/secure the Oracle account and MFA, choose a region with adequate
   current Ampere capacity, and verify the tenancy's A1 quota before creating
   anything. Set budget/usage notifications where available.
2. Create an Ubuntu LTS ARM64 Ampere A1 instance using an SSH keypair you
   control. Start with a small instance (for example 2 OCPUs and 12 GB RAM)
   only if the current region/tenancy permits it within the tier. Account for
   the monthly OCPU/memory hour pool; continuous maximum allocation may
   exceed the free monthly hours depending on the month's length. One
   concurrent scan remains the application default per worker.
3. Allocate encrypted boot/block storage with enough scratch space; 40 GB is a
   practical starting point for static scanning. Monitor capacity; temporary
   archives and Docker layers can consume disk rapidly.
4. Use a reserved public IP only if operationally required. Do not expose
   Django/PostgreSQL/worker ports publicly. Restrict SSH ingress to trusted
   operator IPs. Permit worker outbound traffic only to the shared PostgreSQL
   endpoint, GitHub API/codeload and approved scanner sources. Deny metadata
   and forbidden private/loopback/link-local destinations.
5. Install the same generic worker:

   ```sh
   sudo deploy/linux-worker/install.sh --source /path/to/gw-backend
   ```

   Inject `/etc/securewise/worker.env` via a secret manager or protected
   provisioning process. Keep database TLS settings, Django secrets and
   GitHub App credentials out of shell history and cloud-init output.
6. Run `deploy/linux-worker/verify.sh` and check `uname -m` reports ARM64,
   Python/Django/database health and the installed scanner versions.
   Semgrep/Trivy/Gitleaks/ZAP/Chromium availability must be verified on the
   actual ARM image; Docker/Playwright compatibility is not assumed.
7. Enable the systemd worker and verify its heartbeat and a controlled,
   owned fixture scan in SecureWise. Verify findings/engine states, logs,
   resource ceilings, job recovery and workspace cleanup.
8. If external URL assessment is considered, independently apply and test
   deny-by-default host egress restrictions first. The nftables proof checker
   is not an Oracle network security list installer. No URL egress proof or
   customer target scan is verified by this guide.

## Monitoring and rollback

Monitor VM CPU, memory, boot/scratch disk, network, worker heartbeat and
SecureWise queue/failure metrics. Configure Oracle alarms and backups for the
host configuration without backing up temporary customer source unless the
retention policy explicitly permits it. Stop and disable the worker before
deleting the VM; ensure queued jobs can be claimed by another healthy worker.
Preserve deployment secrets in the secret manager and rotate database
credentials when retiring the instance.

The setup guide is documentation only: current published quotas were checked,
but no Oracle account, tenancy-specific quota, instance, scanner on ARM,
firewall, Always Free eligibility or real scan was verified.
