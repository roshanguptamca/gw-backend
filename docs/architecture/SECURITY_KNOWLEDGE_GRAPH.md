# SecureWise — Security Knowledge Graph Design

> Generated: 2026-07-02 · Branch: `feature/securewise-production-scans`

---

## 1. Current State

SecureWise models relationships as plain Django ForeignKey relations in a relational schema:

```
Organization → Project → Repository
Organization → Scan → ScanEngineResult
Scan → Finding (many-to-one, mutable "latest scan")
Finding → first_seen_scan (immutable)
Organization → ScanPolicy
Organization → GitIntegration
Repository → Integration
```

This is adequate for CRUD and simple queries but cannot express:
- Multi-hop traversal (e.g., "all findings reachable from this dependency across all projects")
- Attack path reasoning (e.g., "this exposed endpoint → calls this vulnerable function → uses this compromised dependency")
- Blast radius analysis (e.g., "if this secret is leaked, what systems/services/data are affected?")
- Temporal causality (e.g., "this finding appeared after this commit, which was introduced by this PR, which was authored by this developer")

## 2. Proposed Knowledge Graph Schema

### 2.1 Node Types

| Node Type | Properties | Source |
|-----------|-----------|--------|
| **Organization** | id, name, slug, risk_score | `SecureWiseOrganization` |
| **Project** | id, name, risk_level, tags | `SecureWiseProject` |
| **Repository** | id, name, url, provider, visibility, default_branch | `SecureWiseRepository` |
| **Branch** | name, is_default, is_protected | Git metadata |
| **Commit** | sha, author, timestamp, message | Git log |
| **PullRequest** | id, url, author, status, branch | GitHub/GitLab API |
| **Scan** | id, type, status, started_at, duration, quality_gate_result | `SecureWiseScan` |
| **ScanEngine** | name, version, tool_used | `SecureWiseScanEngineResult` |
| **Finding** | id, title, severity, confidence, status, fingerprint, first_seen, last_seen | `SecureWiseFinding` |
| **CWE** | id (e.g. CWE-79), name, description, category | MITRE CWE database |
| **OWASPCategory** | id (e.g. A01:2021), name, description | OWASP Top 10 |
| **Dependency** | name, version, ecosystem, license | SCA scan results |
| **Advisory** | id (CVE/GHSA), severity, published_at, fixed_version | OSV/NVD/GitHub Advisory |
| **File** | path, language, last_modified | Repository contents |
| **Endpoint** | url, method, auth_required | API spec / DAST results |
| **Container** | image, tag, registry, base_image | Container scan results |
| **K8sResource** | kind, namespace, name | IaC scan results |
| **CloudResource** | provider, type, region, id | Cloud config scan |
| **Secret** | type (api_key/token/private_key), masked_value, location | Secrets scan |
| **ComplianceControl** | framework, control_id, description, status | Compliance mapping |
| **Ticket** | url, status, assignee, created_at | GitHub Issues / Jira |
| **Developer** | username, email, org_membership_role | GuideWisey User + Membership |

### 2.2 Edge Types

| Edge | From → To | Properties |
|------|-----------|-----------|
| `BELONGS_TO` | Project → Organization | |
| `HAS_REPO` | Project → Repository | |
| `CONNECTED_VIA` | Repository → GitIntegration | |
| `HAS_BRANCH` | Repository → Branch | |
| `ON_BRANCH` | Commit → Branch | |
| `PARENT_OF` | Commit → Commit | |
| `PART_OF_PR` | Commit → PullRequest | |
| `SCANNED` | Scan → Repository | branch, commit_sha |
| `USED_ENGINE` | Scan → ScanEngine | |
| `PRODUCED` | Scan → Finding | first_seen: bool |
| `DETECTED_BY` | Finding → ScanEngine | confidence |
| `IN_FILE` | Finding → File | line_number |
| `AT_ENDPOINT` | Finding → Endpoint | |
| `MAPS_TO_CWE` | Finding → CWE | |
| `MAPS_TO_OWASP` | Finding → OWASPCategory | |
| `AFFECTS` | Advisory → Dependency | version_range |
| `DEPENDS_ON` | Repository → Dependency | manifest_file |
| `USES` | File → Dependency | import statement |
| `EXPOSED_IN` | Secret → File | line_number |
| `GRANTS_ACCESS_TO` | Secret → Endpoint/CloudResource | |
| `RUNS_IN` | Repository → Container | |
| `BASED_ON` | Container → Container | base image |
| `DEPLOYED_AS` | Container → K8sResource | |
| `HOSTED_ON` | K8sResource → CloudResource | |
| `CONTROLS` | ComplianceControl → Finding | status |
| `TRACKED_BY` | Finding → Ticket | |
| `FIXED_BY` | Finding → PullRequest | |
| `INTRODUCED_BY` | Finding → Commit | |
| `AUTHORED_BY` | Commit/PullRequest → Developer | |
| `REVIEWED_BY` | Finding → Developer | |
| `CHILD_OF` | CWE → CWE | hierarchy |
| `SIMILAR_TO` | Finding → Finding | similarity_score |

## 3. Queries the Knowledge Graph Enables

### 3.1 Blast Radius Analysis

**Question:** "If API key `AKIA...` is compromised, what's the blast radius?"

```cypher
MATCH (s:Secret {fingerprint: "secret-xyz"})-[:EXPOSED_IN]->(f:File)
      -[:PART_OF]->(r:Repository)-[:BELONGS_TO]->(p:Project)
MATCH (s)-[:GRANTS_ACCESS_TO]->(target)
MATCH (r)-[:RUNS_IN]->(c:Container)-[:DEPLOYED_AS]->(k:K8sResource)
      -[:HOSTED_ON]->(cloud:CloudResource)
RETURN s, f, r, p, target, c, k, cloud
```

**Why this is hard today:** Requires joining across Finding→File (file_path string match), Repository→Finding (FK), then manual correlation of secret type to what it accesses. No way to express "grants access to" relationships in the relational model.

### 3.2 Cross-Project Dependency Risk

**Question:** "Which projects use log4j < 2.17.1 and have internet-exposed endpoints?"

```cypher
MATCH (d:Dependency {name: "log4j-core"})<-[:DEPENDS_ON]-(r:Repository)
      -[:BELONGS_TO]->(p:Project)
WHERE d.version < "2.17.1"
MATCH (r)<-[:SCANNED]-(scan:Scan)-[:PRODUCED]->(f:Finding)
      -[:AT_ENDPOINT]->(e:Endpoint)
RETURN p.name, r.name, d.version, e.url, f.severity
ORDER BY f.severity DESC
```

**Why this is hard today:** SCA findings are per-project with no cross-project dependency correlation. You'd need to query every project's findings independently and manually join on package name/version.

### 3.3 Attack Path Reasoning

**Question:** "Show me exploitable paths from internet-exposed endpoints to critical data stores."

```cypher
MATCH path = (e:Endpoint {auth_required: false})
      -[:AT_ENDPOINT]-(f1:Finding {status: "open"})
      -[:IN_FILE]->(file:File)-[:USES]->(d:Dependency)
      -[:AFFECTS]-(a:Advisory {severity: "critical"})
MATCH (file)<-[:IN_FILE]-(f2:Finding {scanner_type: "sast", status: "open"})
      -[:MAPS_TO_CWE]->(cwe:CWE {id: "CWE-89"})
RETURN path, f1, f2, a, cwe
```

**Why this is hard today:** SAST findings and DAST findings are only loosely correlated via keyword matching in `ScannerOrchestrator._correlate()`. There's no graph traversal from endpoint → code → dependency → advisory.

## 4. Implementation Strategy

### 4.1 Technology Selection

| Option | Pros | Cons | Recommendation |
|--------|------|------|----------------|
| **Neo4j** | Mature, Cypher is expressive, native graph | Separate infrastructure, operational overhead | Best for full graph features |
| **Apache AGE (PostgreSQL)** | Runs inside existing PostgreSQL, Cypher-compatible | Less mature, limited tooling | Good for gradual adoption |
| **Django + materialized views** | No new infrastructure, familiar | Not a real graph, limited traversal | Insufficient |
| **NetworkX (in-memory)** | Python-native, no infra | Doesn't scale, not persistent | Only for analysis scripts |

**Recommendation:** Start with **Apache AGE** (PostgreSQL extension) to avoid adding new infrastructure. The knowledge graph lives alongside the existing relational data in the same database. Migrate to Neo4j only if graph query performance becomes a bottleneck at scale (>100K nodes).

### 4.2 Hybrid Architecture

The knowledge graph does NOT replace the relational models — it augments them:

```
┌─────────────────────┐     ┌──────────────────────┐
│  Django ORM Layer   │     │  Knowledge Graph      │
│  (CRUD, auth, API)  │────►│  (reasoning, paths,   │
│                     │     │   correlation, AI)     │
│  SecureWiseFinding  │     │                       │
│  SecureWiseScan     │     │  Synced via event      │
│  SecureWiseProject  │     │  hooks on model save   │
│  ...                │     │                       │
└─────────────────────┘     └──────────────────────┘
```

- **Writes** go through Django ORM (source of truth for all CRUD operations)
- **Graph sync** happens via Django signals or post-save hooks that create/update graph nodes and edges
- **Graph queries** power AI reasoning, dashboard analytics, and advanced search
- **API layer** exposes graph-powered endpoints alongside existing REST endpoints

### 4.3 Graph Population Pipeline

1. **On scan completion:** Create/update Scan, Finding, ScanEngine nodes; create PRODUCED, DETECTED_BY, IN_FILE, MAPS_TO_CWE, MAPS_TO_OWASP edges
2. **On dependency parse:** Create Dependency nodes; create DEPENDS_ON edges from Repository; create AFFECTS edges from Advisory data
3. **On git integration sync:** Create Branch, Commit nodes; create ON_BRANCH, PARENT_OF edges
4. **On finding triage:** Update Finding node status; create REVIEWED_BY, TRACKED_BY, FIXED_BY edges
5. **Background enrichment:** CWE hierarchy import, OWASP mapping, advisory database sync

## 5. AI + Knowledge Graph Integration

The knowledge graph's primary value is as context for AI agents:

- **Threat Model Agent:** Traverses Repository → File → Dependency → Advisory → CWE paths to build threat models
- **Triage Agent:** Uses Finding → SIMILAR_TO → Finding edges plus historical triage decisions to predict false positives
- **Blast Radius Agent:** Traverses Secret → GRANTS_ACCESS_TO → CloudResource paths to assess impact
- **Compliance Agent:** Maps Finding → MAPS_TO_CWE → CWE → ComplianceControl to generate compliance reports

Without the graph, AI agents would need enormous context windows to reason about relationships that are implicit in the relational data but explicit in the graph.

## 6. Migration Path

1. **Phase 1:** Install Apache AGE, create initial graph schema, sync Organization/Project/Repository/Scan/Finding nodes on save
2. **Phase 2:** Add CWE/OWASP hierarchy as static graph data; create MAPS_TO edges from findings
3. **Phase 3:** Add Dependency/Advisory nodes from SCA results; create cross-project correlation edges
4. **Phase 4:** Add git history nodes (Commit/Branch/PR); create INTRODUCED_BY edges
5. **Phase 5:** Expose graph-powered API endpoints (blast radius, attack paths, dependency risk)
6. **Phase 6:** Feed graph context to AI agents for enhanced reasoning
