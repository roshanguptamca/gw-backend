# SecureWise — Target Architecture

This document describes the target end-to-end architecture for SecureWise's evolution from a static-analysis
SaaS into a full "repo-to-report" application security testing platform, per the product vision. It builds on
top of the existing real components (data model, RBAC, audit log, report pipeline) documented in
`CURRENT_SECUREWISE_REVIEW.md` and adds the missing runtime/dynamic-testing layer.

---

## 1. High-level pipeline

```mermaid
flowchart TD
    A[User submits Repository URL + Scan Policy] --> B[Repository Ingestion]
    B --> C[CodeUnderstandingEngine]
    C --> D[ApplicationRunPlan generated]
    D --> E{User confirms scan plan}
    E -->|approve| F[Pre-Runtime Static Scans]
    F --> F1[SAST - Semgrep]
    F --> F2[SCA - Trivy]
    F --> F3[Secrets - Gitleaks]
    F --> F4[IaC - Trivy config]
    F --> G[DockerizationEngine]
    G --> H[Container Image Scan - Trivy image]
    H --> I[RuntimeEnvironmentManager]
    I --> I1[Start app in isolated sandbox]
    I1 --> I2[Health check + endpoint discovery]
    I2 --> J[Runtime Testing]
    J --> J1[ZAP DAST - passive + spider + optional active]
    J --> J2[API Scan against live OpenAPI spec]
    J --> J3[Playwright authenticated flows]
    J --> J4[AI Pen-Test Planner scenarios - safe, authorized only]
    J --> K[RuntimeEnvironmentManager teardown]
    F1 & F2 & F3 & F4 & H & J1 & J2 & J3 & J4 --> L[Finding Normalization]
    L --> M[FindingCorrelationEngine]
    M --> N[AIRecommendationEngine]
    N --> O[Unified Report]
    O --> P[Dashboard / PDF / JSON / Executive summary]
```

---

## 2. Component responsibilities

```mermaid
flowchart LR
    subgraph Control Plane [Existing - Real]
        ORG[Organization/Project/Repository models]
        RBAC[Permissions + Membership]
        AUDIT[Audit Log]
        POLICY[Scan Policy]
    end

    subgraph New Understanding Layer
        CUE[CodeUnderstandingEngine]
        ARP[ApplicationRunPlan]
    end

    subgraph New Runtime Layer
        DOCK[DockerizationEngine]
        RTE[RuntimeEnvironmentManager]
    end

    subgraph Existing Static Scanners - Real when tool present
        SAST[SAST - Semgrep]
        SCA[SCA - Trivy]
        SEC[Secrets - Gitleaks]
        IAC[IaC - Trivy config]
    end

    subgraph New Dynamic Layer
        ZAP[ZAP DAST Engine]
        APITEST[Live API Scanner]
        PW[Playwright Engine]
        PENTEST[AI Pen-Test Planner + Executor]
    end

    subgraph Post Processing
        NORM[Finding Normalizer]
        CORR[Finding Correlation Engine]
        AIREC[AI Recommendation Engine - existing, extended]
        REPORT[Unified Report - existing, extended]
    end

    ORG --> CUE --> ARP --> DOCK --> RTE
    ARP --> SAST & SCA & SEC & IAC
    RTE --> ZAP & APITEST & PW & PENTEST
    SAST & SCA & SEC & IAC & ZAP & APITEST & PW & PENTEST --> NORM --> CORR --> AIREC --> REPORT
    POLICY --> ARP
    RBAC -.enforces access to.-> ORG
    AUDIT -.logs every step of.-> RTE
```

---

## 3. Sequencing within a "Full Scan"

```mermaid
sequenceDiagram
    participant U as User
    participant API as SecureWise API
    participant CUE as CodeUnderstandingEngine
    participant DOCK as DockerizationEngine
    participant RTE as RuntimeEnvironmentManager
    participant SCAN as Static Scanners (existing)
    participant DYN as Dynamic Engines (ZAP/API/Playwright/PenTest)
    participant CORR as Correlation + AI
    participant DB as Findings/Report DB

    U->>API: POST /scans (scan_type=full, repository, policy)
    API->>CUE: analyze(repository)
    CUE-->>API: ApplicationRunPlan
    API-->>U: scan plan preview (build cmd, ports, risk notes)
    U->>API: confirm scan
    API->>SCAN: run SAST/SCA/Secrets/IaC (existing orchestrator)
    SCAN-->>DB: findings (pre-runtime)
    API->>DOCK: build_or_validate_image(run_plan)
    DOCK-->>API: image_ref, container_scan findings
    API->>RTE: start_isolated_environment(image_ref, run_plan)
    RTE-->>API: health_check_ok, base_url, discovered endpoints
    API->>DYN: run DAST/API/Playwright/PenTest scenarios (target=base_url only)
    DYN-->>DB: runtime findings + evidence (screenshots/traces/requests)
    API->>RTE: teardown()
    API->>CORR: correlate_and_recommend(all findings)
    CORR-->>DB: unified findings with correlation_group + ai_fix_suggestion
    API-->>U: Unified Report ready
```

---

## 4. Isolation & authorization boundaries (non-negotiable)

```mermaid
flowchart TD
    subgraph Trust boundary: SecureWise control plane
        API[SecureWise API/DB]
    end
    subgraph Trust boundary: Ephemeral scan sandbox - per scan
        WS[Scan workspace - tmp dir, deleted after scan]
        NET[Isolated docker network - no host network, no internet except declared deps]
        APP[Target application container - resource-limited, non-privileged]
        TOOLS[Scanner containers - ZAP, Playwright, ai-pentest-runner]
    end
    API -->|creates + destroys| WS
    API -->|creates + destroys| NET
    WS --> APP
    NET --> APP
    NET --> TOOLS
    TOOLS -->|attacks only| APP
    TOOLS -.never reaches.-> Internet((Public internet))
    API -.enforces.-> AuthCheck{Repository/target ownership confirmed?}
    AuthCheck -->|no| Reject[Scan rejected]
    AuthCheck -->|yes| WS
```

Key rules encoded in this boundary (carried through every subsequent design doc):

1. Dynamic/pentest testing **only** ever targets the ephemeral container SecureWise itself started, or a URL
   the user has explicitly attested ownership/authorization for (tracked via a new
   `target_authorization_confirmed` + `target_authorization_note` field on `SecureWiseScan`).
2. No scan sandbox has outbound internet access except to resolve declared package/dependency registries
   needed to build the app (allow-listed).
3. Containers run non-privileged, with CPU/memory/pids/time limits, and are destroyed unconditionally at the
   end of the scan (including on error/timeout paths).
4. No destructive test payloads (data deletion, real credential brute force, DoS) run in MVP — this is
   enforced at the `PenTestPlan.destructive` flag level (see `AI_PENTEST_PLANNER.md`) and rejected by the
   executor if `destructive=true`.

---

## 5. Where this plugs into the existing (real) codebase

- `SecureWiseScan.scan_type` already has a `full` option (`models.py`) — the new orchestrator becomes the
  handler for `full`, extending (not replacing) the existing `services/scanner.py::ScannerRunner`.
- `SecureWiseScanEngineResult` already models per-engine results generically enough to add new engine types
  (`dockerize`, `runtime_start`, `zap_dast`, `playwright`, `ai_pentest`) without a schema change beyond
  extending the `scanner_type` choices.
- `SecureWiseFinding` needs the additive fields described in `UNIFIED_FINDING_MODEL.md`
  (`exploitability`, `cvss`, `correlation_group`, `retest_status`) — additive migration, no breaking change.
- The existing `AuditLog` + `_audit()` helper (`views.py:74-87`) should be used for every new lifecycle event
  (`runtime.start`, `runtime.stop`, `dockerize.build`, `pentest.scenario_run`) — no new logging mechanism
  needed.
- Async execution: this is the point at which the current thread-based MVP execution model becomes
  insufficient (see Phase 1 in `IMPLEMENTATION_ROADMAP.md`) — a real queue (Celery + Redis, or RQ) is a
  prerequisite for safely running multi-minute build+runtime+dynamic-scan jobs concurrently across tenants.
