"""
Recommendation engine — provides structured remediation guidance for
findings across languages/frameworks, with a generic fallback for anything
not explicitly templated.
"""

from __future__ import annotations

from .cwe_mapping import map_finding

# (language_or_framework, issue_key) -> template dict
_TEMPLATES: dict[tuple[str, str], dict] = {
    # -------------------------------------------------------------- Python
    ("python", "sql_injection"): {
        "what": "User-controlled input is concatenated or interpolated directly into a SQL statement.",
        "why": "Attackers can inject arbitrary SQL, reading/modifying/deleting data or bypassing authentication.",
        "where": "Anywhere raw SQL strings are built from request data (views, models, raw cursor.execute calls).",
        "how_to_fix": "Use parameterized queries or the Django/SQLAlchemy ORM instead of string formatting.",
        "bad_code_example": 'query = "SELECT * FROM users WHERE id=" + user_id\ncursor.execute(query)',
        "fixed_code_example": 'cursor.execute("SELECT * FROM users WHERE id=%s", [user_id])',
        "auto_fix_possible": False,
        "references": ["https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html"],
    },
    ("python", "command_injection"): {
        "what": "User input reaches a shell command (subprocess with shell=True, os.system, os.popen).",
        "why": "Attackers can execute arbitrary OS commands with the privileges of the application.",
        "where": "subprocess/os.system calls that build a command string from request data.",
        "how_to_fix": "Avoid shell=True; pass args as a list, validate/allowlist input, or use safer APIs.",
        "bad_code_example": 'subprocess.run(f"ping {host}", shell=True)',
        "fixed_code_example": 'subprocess.run(["ping", host], shell=False)',
        "auto_fix_possible": False,
        "references": ["https://cheatsheetseries.owasp.org/cheatsheets/OS_Command_Injection_Defense_Cheat_Sheet.html"],
    },
    ("python", "path_traversal"): {
        "what": "A file path is built from user input without normalization/allowlisting.",
        "why": "Attackers can read or write files outside the intended directory (e.g. ../../etc/passwd).",
        "where": "File open/serve endpoints that accept a filename or path parameter.",
        "how_to_fix": "Resolve the path, verify it is contained within an allowed base directory before use.",
        "bad_code_example": "open(os.path.join(base_dir, request.GET['file']))",
        "fixed_code_example": (
            "p = (base_dir / request.GET['file']).resolve()\n"
            "if not str(p).startswith(str(base_dir.resolve())):\n"
            "    raise SuspiciousOperation()"
        ),
        "auto_fix_possible": False,
        "references": ["https://owasp.org/www-community/attacks/Path_Traversal"],
    },
    ("python", "unsafe_pickle"): {
        "what": "pickle.loads()/pickle.load() is used on data that may originate from an untrusted source.",
        "why": "Deserializing untrusted pickle data can lead to arbitrary remote code execution.",
        "where": "Cache layers, message queues, or any endpoint that deserializes user-supplied bytes.",
        "how_to_fix": "Use JSON or another safe serialization format. Never unpickle untrusted input.",
        "bad_code_example": "data = pickle.loads(request.body)",
        "fixed_code_example": "data = json.loads(request.body)",
        "auto_fix_possible": False,
        "references": ["https://docs.python.org/3/library/pickle.html#module-pickle"],
    },
    ("python", "unsafe_yaml_load"): {
        "what": "yaml.load() is called without SafeLoader, allowing arbitrary Python object construction.",
        "why": "Malicious YAML can execute arbitrary code during deserialization.",
        "where": "Config loaders or endpoints that parse YAML supplied by users.",
        "how_to_fix": "Use yaml.safe_load() (or yaml.load(data, Loader=yaml.SafeLoader)).",
        "bad_code_example": "config = yaml.load(f)",
        "fixed_code_example": "config = yaml.safe_load(f)",
        "auto_fix_possible": True,
        "references": ["https://pyyaml.org/wiki/PyYAMLDocumentation"],
    },
    ("python", "debug_enabled"): {
        "what": "DEBUG = True is set, which is unsafe in a production Django deployment.",
        "why": "Debug pages leak stack traces, settings, and environment details to attackers.",
        "where": "settings.py or environment-derived Django settings.",
        "how_to_fix": "Set DEBUG = False in production and drive it from an environment variable.",
        "bad_code_example": "DEBUG = True",
        "fixed_code_example": "DEBUG = os.environ.get('DJANGO_DEBUG', 'False') == 'True'",
        "auto_fix_possible": True,
        "references": ["https://docs.djangoproject.com/en/stable/ref/settings/#debug"],
    },
    ("python", "missing_csrf"): {
        "what": "A state-changing view disables or omits CSRF protection.",
        "why": "Without CSRF protection, attackers can trick authenticated users into performing unwanted actions.",
        "where": "Views decorated with @csrf_exempt or missing Django's CSRF middleware.",
        "how_to_fix": "Remove @csrf_exempt where not strictly required and ensure CsrfViewMiddleware is enabled.",
        "bad_code_example": "@csrf_exempt\ndef transfer_funds(request): ...",
        "fixed_code_example": "def transfer_funds(request): ...  # protected by CsrfViewMiddleware",
        "auto_fix_possible": False,
        "references": ["https://docs.djangoproject.com/en/stable/ref/csrf/"],
    },
    ("python", "missing_permission_checks"): {
        "what": "An endpoint does not verify the caller is authorized to perform the requested action.",
        "why": "Any authenticated (or even anonymous) user could access or modify data they should not.",
        "where": "DRF views/viewsets missing permission_classes, or missing object-level checks.",
        "how_to_fix": "Add explicit permission_classes and object-level ownership/role checks.",
        "bad_code_example": "class ScanViewSet(viewsets.ModelViewSet):\n    permission_classes = []",
        "fixed_code_example": "class ScanViewSet(viewsets.ModelViewSet):\n    permission_classes = [IsAuthenticated, IsOrgMember]",
        "auto_fix_possible": False,
        "references": ["https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html"],
    },
    ("python", "weak_crypto"): {
        "what": "MD5 or SHA1 is used in a security-sensitive context such as password hashing.",
        "why": "MD5/SHA1 are cryptographically broken/weak and unsuitable for password or integrity protection.",
        "where": "Auth/password handling code.",
        "how_to_fix": "Use Django's password hashers (PBKDF2/Argon2) or bcrypt/scrypt/argon2-cffi directly.",
        "bad_code_example": "hashlib.md5(password.encode()).hexdigest()",
        "fixed_code_example": "from django.contrib.auth.hashers import make_password\nmake_password(password)",
        "auto_fix_possible": False,
        "references": ["https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html"],
    },
    ("python", "hardcoded_secrets"): {
        "what": "A credential/API key/secret is hardcoded as a string literal in source code.",
        "why": "Anyone with source access (including via VCS history) obtains the secret.",
        "where": "Config modules, settings files, client SDK initialization code.",
        "how_to_fix": "Load secrets from environment variables or a secrets manager; rotate the exposed secret.",
        "bad_code_example": 'API_KEY = "hardcoded-plaintext-secret-value-do-not-do-this"',
        "fixed_code_example": 'API_KEY = os.environ["API_KEY"]',
        "auto_fix_possible": False,
        "references": ["https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html"],
    },
    # ---------------------------------------------------------------- Java
    ("java", "sql_injection"): {
        "what": "A SQL statement is built via string concatenation with request parameters.",
        "why": "Allows attackers to manipulate query logic and access unauthorized data.",
        "where": "JDBC Statement usage, or JPQL/HQL built via string concatenation.",
        "how_to_fix": "Use PreparedStatement with bind parameters, or parameterized JPQL/Criteria API.",
        "bad_code_example": 'stmt.executeQuery("SELECT * FROM users WHERE id=" + id);',
        "fixed_code_example": (
            'PreparedStatement ps = conn.prepareStatement("SELECT * FROM users WHERE id=?");\n'
            "ps.setString(1, id);"
        ),
        "auto_fix_possible": False,
        "references": ["https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html"],
    },
    ("java", "xxe"): {
        "what": "An XML parser is configured without disabling external entity resolution.",
        "why": "Attackers can read local files, perform SSRF, or cause denial of service via XXE payloads.",
        "where": "DocumentBuilderFactory/SAXParserFactory/XMLInputFactory configuration.",
        "how_to_fix": "Disable DOCTYPE declarations and external entities on the parser factory.",
        "bad_code_example": "DocumentBuilderFactory dbf = DocumentBuilderFactory.newInstance();",
        "fixed_code_example": (
            "DocumentBuilderFactory dbf = DocumentBuilderFactory.newInstance();\n"
            'dbf.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);'
        ),
        "auto_fix_possible": True,
        "references": ["https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html"],
    },
    ("java", "unsafe_deserialization"): {
        "what": "ObjectInputStream.readObject() is used on data from an untrusted source.",
        "why": "Malicious serialized objects can trigger gadget chains leading to remote code execution.",
        "where": "Any endpoint or message consumer that deserializes raw Java objects.",
        "how_to_fix": "Avoid native Java serialization for untrusted input; use JSON with a schema-validating parser.",
        "bad_code_example": "Object o = new ObjectInputStream(in).readObject();",
        "fixed_code_example": "MyDto dto = objectMapper.readValue(in, MyDto.class);",
        "auto_fix_possible": False,
        "references": ["https://cheatsheetseries.owasp.org/cheatsheets/Deserialization_Cheat_Sheet.html"],
    },
    ("java", "missing_authorization"): {
        "what": "A controller endpoint has no @PreAuthorize/role check for a sensitive operation.",
        "why": "Any authenticated (or anonymous) caller may invoke privileged functionality.",
        "where": "Spring MVC/REST controllers.",
        "how_to_fix": "Add @PreAuthorize/@Secured annotations or explicit checks matching the required role.",
        "bad_code_example": "@PostMapping(\"/admin/users/{id}/delete\")\npublic void delete(@PathVariable id) { ... }",
        "fixed_code_example": (
            "@PreAuthorize(\"hasRole('ADMIN')\")\n"
            "@PostMapping(\"/admin/users/{id}/delete\")\n"
            "public void delete(@PathVariable id) { ... }"
        ),
        "auto_fix_possible": False,
        "references": ["https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html"],
    },
    ("java", "weak_crypto"): {
        "what": "DES/MD5/SHA1 is used for encryption or hashing of sensitive data.",
        "why": "These algorithms are broken or too weak for modern security requirements.",
        "where": "Cipher.getInstance(...) or MessageDigest.getInstance(...) calls.",
        "how_to_fix": "Use AES-GCM for encryption and BCrypt/Argon2 for password hashing.",
        "bad_code_example": 'Cipher.getInstance("DES");',
        "fixed_code_example": 'Cipher.getInstance("AES/GCM/NoPadding");',
        "auto_fix_possible": False,
        "references": ["https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html"],
    },
    # ------------------------------------------------------------ JS/Node
    ("javascript", "xss"): {
        "what": "User-controlled data is inserted into the DOM without escaping (innerHTML, dangerouslySetInnerHTML).",
        "why": "Attackers can inject and execute arbitrary JavaScript in victims' browsers.",
        "where": "React components, template rendering, or direct DOM manipulation.",
        "how_to_fix": "Use textContent or a sanitizer (DOMPurify) before rendering user-controlled HTML.",
        "bad_code_example": "element.innerHTML = userInput;",
        "fixed_code_example": "element.textContent = userInput; // or DOMPurify.sanitize(userInput)",
        "auto_fix_possible": False,
        "references": ["https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html"],
    },
    ("javascript", "eval_usage"): {
        "what": "eval() or new Function() is used, potentially with user-influenced input.",
        "why": "Arbitrary code execution if the evaluated string is attacker-controlled.",
        "where": "Anywhere dynamic code execution is used instead of safer alternatives.",
        "how_to_fix": "Avoid eval/new Function; use JSON.parse for data, or explicit dispatch tables for logic.",
        "bad_code_example": "eval(userInput);",
        "fixed_code_example": "JSON.parse(userInput);",
        "auto_fix_possible": False,
        "references": ["https://cheatsheetseries.owasp.org/cheatsheets/DOM_based_XSS_Prevention_Cheat_Sheet.html"],
    },
    ("javascript", "prototype_pollution"): {
        "what": "Untrusted keys are merged into an object recursively without guarding __proto__/constructor.",
        "why": "Attackers can pollute Object.prototype, leading to DoS or, in some cases, RCE.",
        "where": "Deep-merge/clone utilities, lodash-style merges on user-supplied JSON.",
        "how_to_fix": "Reject/skip __proto__, constructor and prototype keys during merges; use Object.create(null).",
        "bad_code_example": "merge(target, JSON.parse(userInput));",
        "fixed_code_example": (
            "if (['__proto__', 'constructor', 'prototype'].includes(key)) continue;\n"
            "merge(target, safeInput);"
        ),
        "auto_fix_possible": False,
        "references": ["https://portswigger.net/web-security/prototype-pollution"],
    },
    ("javascript", "insecure_jwt"): {
        "what": "A JWT is decoded/verified with 'none' algorithm allowed or without signature verification.",
        "why": "Attackers can forge tokens and impersonate any user.",
        "where": "Auth middleware that decodes JWTs.",
        "how_to_fix": "Explicitly allowlist the signing algorithm(s) and always verify the signature.",
        "bad_code_example": "jwt.decode(token); // no verification",
        "fixed_code_example": "jwt.verify(token, secret, { algorithms: ['HS256'] });",
        "auto_fix_possible": False,
        "references": ["https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html"],
    },
    ("javascript", "missing_helmet_headers"): {
        "what": "An Express app does not use helmet() or equivalent security headers middleware.",
        "why": "Missing security headers (CSP, HSTS, X-Frame-Options, etc.) increase exposure to common attacks.",
        "where": "Express/Node app bootstrap.",
        "how_to_fix": "Add const helmet = require('helmet'); app.use(helmet());",
        "bad_code_example": "const app = express();",
        "fixed_code_example": "const app = express();\napp.use(helmet());",
        "auto_fix_possible": True,
        "references": ["https://helmetjs.github.io/"],
    },
    ("javascript", "command_injection"): {
        "what": "child_process.exec() is called with a string built from user input.",
        "why": "Attackers can inject shell metacharacters and execute arbitrary commands.",
        "where": "Any use of exec()/execSync() with concatenated input.",
        "how_to_fix": "Use execFile()/spawn() with an argument array instead of a shell string.",
        "bad_code_example": "exec(`convert ${filename} out.png`);",
        "fixed_code_example": "execFile('convert', [filename, 'out.png']);",
        "auto_fix_possible": False,
        "references": ["https://cheatsheetseries.owasp.org/cheatsheets/OS_Command_Injection_Defense_Cheat_Sheet.html"],
    },
    # ----------------------------------------------------------------- Go
    ("go", "sql_injection"): {
        "what": "A SQL query string is built via fmt.Sprintf with user input instead of placeholders.",
        "why": "Allows attackers to alter query semantics and access unauthorized data.",
        "where": "database/sql Query/Exec calls built with string formatting.",
        "how_to_fix": "Use parameterized queries with placeholders ($1, ?) passed as Query args.",
        "bad_code_example": 'db.Query(fmt.Sprintf("SELECT * FROM users WHERE id=%s", id))',
        "fixed_code_example": 'db.Query("SELECT * FROM users WHERE id=$1", id)',
        "auto_fix_possible": False,
        "references": ["https://go.dev/doc/database/sql-injection"],
    },
    ("go", "command_injection"): {
        "what": "os/exec.Command is invoked through a shell with unsanitized user input.",
        "why": "Attackers can inject shell metacharacters to execute arbitrary commands.",
        "where": "exec.Command(\"sh\", \"-c\", userInput) style calls.",
        "how_to_fix": "Call the target binary directly with an argument slice; avoid invoking a shell.",
        "bad_code_example": 'exec.Command("sh", "-c", "ping " + host)',
        "fixed_code_example": 'exec.Command("ping", host)',
        "auto_fix_possible": False,
        "references": ["https://cheatsheetseries.owasp.org/cheatsheets/OS_Command_Injection_Defense_Cheat_Sheet.html"],
    },
    ("go", "path_traversal"): {
        "what": "http.ServeFile or os.Open is called with an unsanitized path from a request.",
        "why": "Attackers may read arbitrary files outside the intended directory.",
        "where": "File-serving handlers.",
        "how_to_fix": "Use filepath.Clean plus a containment check against the allowed base directory.",
        "bad_code_example": "http.ServeFile(w, r, filepath.Join(base, r.URL.Query().Get(\"file\")))",
        "fixed_code_example": (
            "p := filepath.Clean(filepath.Join(base, r.URL.Query().Get(\"file\")))\n"
            "if !strings.HasPrefix(p, base) { http.Error(w, \"forbidden\", 403); return }"
        ),
        "auto_fix_possible": False,
        "references": ["https://owasp.org/www-community/attacks/Path_Traversal"],
    },
    ("go", "missing_timeouts"): {
        "what": "An http.Client or http.Server is created without explicit timeouts.",
        "why": "Slow or malicious peers can exhaust server resources (slowloris-style DoS).",
        "where": "http.Client{}/http.Server{} construction.",
        "how_to_fix": "Set Timeout on http.Client and ReadTimeout/WriteTimeout on http.Server.",
        "bad_code_example": "client := &http.Client{}",
        "fixed_code_example": "client := &http.Client{Timeout: 10 * time.Second}",
        "auto_fix_possible": True,
        "references": ["https://blog.cloudflare.com/the-complete-guide-to-golang-net-http-timeouts/"],
    },
    ("go", "weak_tls"): {
        "what": "A tls.Config sets InsecureSkipVerify: true or allows deprecated TLS versions.",
        "why": "Disables certificate validation, enabling man-in-the-middle attacks.",
        "where": "tls.Config construction for HTTP clients or servers.",
        "how_to_fix": "Remove InsecureSkipVerify and set MinVersion: tls.VersionTLS12 or higher.",
        "bad_code_example": "tls.Config{InsecureSkipVerify: true}",
        "fixed_code_example": "tls.Config{MinVersion: tls.VersionTLS12}",
        "auto_fix_possible": True,
        "references": ["https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html"],
    },
    # ------------------------------------------------------------- Generic
    ("generic", "leaked_secret"): {
        "what": "A credential/API key/token was found committed to the repository.",
        "why": "Anyone with repository access (including via history) can use the exposed credential.",
        "where": "Source files, .env files, configuration, or commit history.",
        "how_to_fix": "Revoke/rotate the secret immediately, remove it from history, and use a secrets manager.",
        "bad_code_example": 'AWS_SECRET_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"',
        "fixed_code_example": "AWS_SECRET_ACCESS_KEY = os.environ['AWS_SECRET_ACCESS_KEY']",
        "auto_fix_possible": False,
        "references": ["https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html"],
    },
    ("generic", "vulnerable_dependency"): {
        "what": "A dependency pinned in the manifest has a known published CVE.",
        "why": "Exploits for known CVEs are often public, making outdated dependencies an easy attack target.",
        "where": "requirements.txt/package.json/pom.xml/go.mod and other dependency manifests.",
        "how_to_fix": "Upgrade the dependency to a patched version referenced in the CVE advisory.",
        "bad_code_example": "requests==2.28.0",
        "fixed_code_example": "requests>=2.31.0",
        "auto_fix_possible": True,
        "references": ["https://osv.dev/"],
    },
    ("generic", "insecure_dockerfile"): {
        "what": "The Dockerfile runs as root and/or pins an unpinned (:latest) or missing base image tag.",
        "why": "Running containers as root increases blast radius of a container escape; :latest is non-reproducible.",
        "where": "Dockerfile.",
        "how_to_fix": "Pin a specific base image digest/tag and add a non-root USER instruction.",
        "bad_code_example": "FROM python:latest\n# ... no USER instruction",
        "fixed_code_example": "FROM python:3.12-slim\nRUN useradd -m appuser\nUSER appuser",
        "auto_fix_possible": True,
        "references": ["https://cheatsheetseries.owasp.org/cheatsheets/Docker_Security_Cheat_Sheet.html"],
    },
    ("generic", "k8s_privileged_container"): {
        "what": "A Kubernetes pod/container spec sets privileged: true or hostNetwork: true.",
        "why": "Privileged containers can access host devices/kernel, enabling container breakout.",
        "where": "Kubernetes manifests (Deployment/Pod/DaemonSet securityContext).",
        "how_to_fix": "Remove privileged/hostNetwork, apply least-privilege securityContext, add resource limits.",
        "bad_code_example": "securityContext:\n  privileged: true",
        "fixed_code_example": "securityContext:\n  privileged: false\n  runAsNonRoot: true",
        "auto_fix_possible": False,
        "references": ["https://kubernetes.io/docs/concepts/security/pod-security-standards/"],
    },
    ("generic", "missing_security_headers"): {
        "what": "HTTP responses lack security headers such as CSP, X-Frame-Options, HSTS, X-Content-Type-Options.",
        "why": "Missing headers weaken protection against clickjacking, MIME sniffing, and downgrade attacks.",
        "where": "Web server / application middleware configuration.",
        "how_to_fix": "Add the relevant security headers at the middleware/proxy layer.",
        "bad_code_example": "# no security headers configured",
        "fixed_code_example": (
            "response['Content-Security-Policy'] = \"default-src 'self'\"\n"
            "response['X-Frame-Options'] = 'DENY'\n"
            "response['Strict-Transport-Security'] = 'max-age=63072000'"
        ),
        "auto_fix_possible": True,
        "references": ["https://owasp.org/www-project-secure-headers/"],
    },
    ("generic", "cors_wildcard"): {
        "what": "Access-Control-Allow-Origin: * is combined with credentialed requests.",
        "why": "Any origin can read authenticated responses, defeating same-origin protections.",
        "where": "CORS middleware configuration.",
        "how_to_fix": "Use an explicit origin allowlist and only enable credentials for trusted origins.",
        "bad_code_example": "Access-Control-Allow-Origin: *\nAccess-Control-Allow-Credentials: true",
        "fixed_code_example": "Access-Control-Allow-Origin: https://app.example.com\nAccess-Control-Allow-Credentials: true",
        "auto_fix_possible": False,
        "references": ["https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html"],
    },
}

_ISSUE_TO_MAPPING_KEY = {
    "sql_injection": "sql_injection",
    "xss": "xss",
    "command_injection": "command_injection",
    "path_traversal": "path_traversal",
    "unsafe_pickle": "insecure_deserialization",
    "unsafe_yaml_load": "insecure_deserialization",
    "debug_enabled": "missing_security_headers",
    "missing_csrf": "csrf",
    "missing_permission_checks": "missing_authorization",
    "weak_crypto": "weak_crypto",
    "hardcoded_secrets": "hardcoded_secret",
    "leaked_secret": "hardcoded_secret",
    "xxe": "xxe",
    "unsafe_deserialization": "insecure_deserialization",
    "missing_authorization": "missing_authorization",
    "prototype_pollution": "prototype_pollution",
    "insecure_jwt": "missing_authorization",
    "missing_helmet_headers": "missing_security_headers",
    "eval_usage": "command_injection",
    "missing_timeouts": "missing_security_headers",
    "weak_tls": "weak_tls",
    "vulnerable_dependency": "vulnerable_dependency",
    "insecure_dockerfile": "iac_misconfiguration",
    "k8s_privileged_container": "iac_misconfiguration",
    "cors_wildcard": "insecure_cors",
}


class RecommendationEngine:
    """Provides remediation guidance for a given (issue_key, language)."""

    @staticmethod
    def get_recommendation(issue_key: str, language: str = "generic") -> dict:
        language = (language or "generic").lower()
        template = _TEMPLATES.get((language, issue_key)) or _TEMPLATES.get(("generic", issue_key))
        if template is None:
            template = {
                "what": f"A potential {issue_key.replace('_', ' ')} issue was detected.",
                "why": "This class of issue commonly leads to security weaknesses if left unaddressed.",
                "where": "See the reported file/location for this finding.",
                "how_to_fix": "Review the affected code/config and apply the relevant OWASP guidance.",
                "bad_code_example": "",
                "fixed_code_example": "",
                "auto_fix_possible": False,
                "references": ["https://owasp.org/Top10/"],
            }
        mapping_key = _ISSUE_TO_MAPPING_KEY.get(issue_key, issue_key)
        cwe = map_finding(mapping_key)
        result = dict(template)
        result["cwe_id"] = cwe["cwe_id"]
        result["owasp_category"] = cwe["owasp_category"]
        result["recommendation"] = template["how_to_fix"]
        return result
