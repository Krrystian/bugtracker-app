# Rejestr podatności (branche `vuln/*`)

Każda podatność istnieje **wyłącznie** na własnym, długo żyjącym branchu `vuln/<nazwa>`, który **nigdy nie jest scalany do `main`**. Każdy branch psuje dokładnie jedną rzecz i ma zostać zatrzymany przez **jedną, zaplanowaną bramkę**; pozostałe joby CI mają być zielone. W kodzie podatne miejsca są oznaczone komentarzem `VULN-XX`.

`main` = wersja secure (poprawka opisana w kolumnie „Poprawka w `main`”).

| ID | Branch | Repo | Kategoria OWASP | Bramka, która ma zatrzymać | Etap | Status |
|---|---|---|---|---|---|---|
| VULN-01 | `vuln/secret-leak` | app | A07:2021 Identification and Authentication Failures (CWE-798) | Gitleaks | 11f | planowany |
| VULN-02 | `vuln/dockerfile-bad-practices` | app | A05:2021 Security Misconfiguration | Hadolint | 11g | planowany |
| VULN-03 | `vuln/sast-code` | app | A03:2021 Injection, A02:2021 Cryptographic Failures | **Semgrep (SAST)** | 11a | **utworzony** |
| VULN-04 | `vuln/sca-deps` | app | A06:2021 Vulnerable and Outdated Components | OSV-Scanner (SCA), test T1 | 11b | planowany |
| VULN-05 | `vuln/image-cve` | app | A06:2021 Vulnerable and Outdated Components | Trivy `image` | 11h | planowany |
| VULN-06 | `vuln/helm-privileged` | app | A05:2021 Security Misconfiguration | Checkov, test T2 | 11c | planowany |
| VULN-07 | `vuln/helm-no-netpol` | app | A05:2021 Security Misconfiguration | Checkov / test w klastrze | 11c, 14 | planowany |
| VULN-08 | `vuln/dast-runtime` | app | A05:2021 Security Misconfiguration | OWASP ZAP (DAST) | 11e | planowany |
| VULN-09 | `vuln/unsigned-image` | gitops | A08:2021 Software and Data Integrity Failures | Kyverno (admission), test T3 | 14 | planowany |
| VULN-10 | `vuln/plaintext-secret` | gitops | A02:2021 Cryptographic Failures (CWE-312) | Gitleaks na repo GitOps | 12 | planowany |

---

## VULN-03: podatny kod aplikacji (SAST)

- **Branch:** `vuln/sast-code`
- **Bramka:** job `SAST (Semgrep)`. Pozostałe joby (`Unit tests`, `Build image`) zielone.
- **Co psujemy:** nowa strona wyszukiwania `/ui/search?q=...` w `app/web.py` i `app/templates/search.html`:

| Podatność | CWE | Miejsce | Reguła Semgrep | Poziom |
|---|---|---|---|---|
| SQL injection: parametr `q` doklejany do surowego zapytania SQL (`text(...)`) | CWE-89 | `app/web.py` | `python.sqlalchemy.security.audit.avoid-sqlalchemy-text` | error (blokuje) |
| XSS: wynik wyszukiwania renderowany z filtrem `\|safe` (bez escapowania HTML) | CWE-79 | `app/templates/search.html` | `jinja2-autoescape-disabled-in-template` (reguła projektu, `.semgrep/rules.yml`) | error (blokuje) |
| Słaby hash: MD5 jako „odcisk” zapytania | CWE-327 | `app/web.py` | `python.lang.security.insecure-hash-algorithms-md5` | warning (raportowany) |

- **Poprawka w `main`:**
  - wszystkie zapytania przez ORM SQLAlchemy (`select(...)`, parametry wiązane), brak `text()` z danymi użytkownika,
  - Jinja2 z `autoescape=True`, brak `|safe` i `Markup()` na danych użytkownika, dodatkowo ścisłe CSP (`default-src 'none'`),
  - hasła hashowane Argon2id, brak MD5/SHA1 w kontekście bezpieczeństwa.
