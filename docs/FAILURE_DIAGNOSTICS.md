# Failure Diagnostics

SecureWise should classify failures by stage and surface a sanitized log excerpt.

## Failure stages

- repository_validation_failed
- clone_failed
- discovery_failed
- runtime_plan_failed
- dockerfile_generation_failed
- dependency_install_failed
- docker_build_failed
- dependency_service_failed
- migration_failed
- application_start_failed
- port_discovery_failed
- health_check_failed
- runtime_timeout
- dast_failed
- cleanup_failed

## Required fields

- stage
- short_summary
- sanitized_log_excerpt
- root_cause
- suggested_fix
- retryable
- retry_attempts

## Guidance

Diagnostics should explain the real blocker, not hide behind a generic Docker error.
The SecureWise frontend now consumes `diagnostics.log_excerpt`, shows the failed stage, and
renders retry guidance inline on the scan detail page. When `retryable` is true, the UI shows a
retry action; when it is false, the retry action is hidden and the page stays honest about partial
coverage.
