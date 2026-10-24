# Rejestr podatności (branche `vuln/*`)

Każda podatność istnieje **wyłącznie** na własnym, długo żyjącym branchu `vuln/<nazwa>`, który **nigdy nie jest scalany do `main`**. Każdy branch psuje dokładnie jedną rzecz i ma zostać zatrzymany przez **jedną, zaplanowaną bramkę**; pozostałe joby CI mają być zielone. W kodzie podatne miejsca są oznaczone komentarzem `VULN-XX`.

`main` = wersja secure (poprawka opisana w kolumnie „Poprawka w `main`”).

| ID | Branch | Repo | Kategoria OWASP | Bramka, która ma zatrzymać | Etap | Status |
|---|---|---|---|---|---|---|
| VULN-01 | `vuln/secret-leak` | app | A07:2021 Identification and Authentication Failures (CWE-798) | Gitleaks | 11f | planowany |
| VULN-02 | `vuln/dockerfile-bad-practices` | app | A05:2021 Security Misconfiguration | Hadolint | 11g | planowany |
| VULN-03 | `vuln/sast-code` | app | A03:2021 Injection, A02:2021 Cryptographic Failures | **Semgrep (SAST)** | 11a | ✅ zatrzymany przez Semgrep |
| VULN-04 | `vuln/sca-deps` | app | A06:2021 Vulnerable and Outdated Components | **OSV-Scanner (SCA)**, test T1 | 11b | ✅ zatrzymany przez OSV-Scanner |
| VULN-05 | `vuln/image-cve` | app | A06:2021 Vulnerable and Outdated Components | Trivy `image` | 11h | planowany |
| VULN-06 | `vuln/helm-privileged` | app | A05:2021 Security Misconfiguration | **Checkov**, test T2 | 11c | ✅ zatrzymany przez Checkov |
| VULN-07 | `vuln/helm-no-netpol` | app | A05:2021 Security Misconfiguration | **Checkov** / test w klastrze | 11c, 14 | ✅ zatrzymany przez Checkov (klaster: etap 14) |
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

---

## VULN-04: przestarzała biblioteka z krytyczną CVE (SCA)

- **Branch:** `vuln/sca-deps`
- **Bramka:** job `SCA (OSV-Scanner)`. Pozostałe joby zielone (test T1).
- **Co psujemy:** do `requirements.in` (i lock file `requirements.txt`) dodany klient HTTP **`urllib3==1.22`** (2017 r.).
- **Najważniejsza podatność:** [CVE-2018-20060](https://osv.dev/PYSEC-2018-32) / PYSEC-2018-32, **CVSS 9.8 (Critical)** — przy przekierowaniu na inny host urllib3 przekazuje dalej nagłówek `Authorization`, więc dane logowania mogą trafić do obcego serwera (CWE-200). Wersja ma też kilka podatności High (CVSS 8.9).
- **Poprawka w `main`:** biblioteka nieużywana — nie występuje; wszystkie zależności (także przechodnie) przypięte w lock files i skanowane przy każdym PR. Gdyby była potrzebna: `urllib3>=2.x` (aktualna wersja bez znanych podatności).

---

## VULN-06: wykres Helm z kontenerem root, `privileged` i bez limitów (IaC)

- **Branch:** `vuln/helm-privileged`
- **Bramka:** job `IaC (Checkov)`. Pozostałe joby zielone (test T2 — część statyczna).
- **Co psujemy** (`charts/bugtracker/values.yaml`, wartości domyślne):
  - `podSecurityContext`: `runAsNonRoot: false`, `runAsUser: 0` — kontenery jako root (CWE-250),
  - `securityContext`: `privileged: true`, `allowPrivilegeEscalation: true`, `readOnlyRootFilesystem: false`, brak `capabilities.drop` (CWE-269),
  - `app.resources: {}` — brak requests/limits (CWE-770).
- **Wykrywa:** CKV_K8S_11, 13, 16, 20, 22, 23, 28, 31, 37, 40 (15 znalezisk High).
- **Poprawka w `main`:** UID 10001 / 70, `runAsNonRoot: true`, `privileged` nieustawione, `allowPrivilegeEscalation: false`, read-only root FS, `capabilities.drop: [ALL]`, `seccompProfile: RuntimeDefault`, limity CPU/RAM; dodatkowo namespace z Pod Security `restricted` (taki pod nie zostałby przyjęty przez klaster).

## VULN-07: wykres Helm bez NetworkPolicy (IaC)

- **Branch:** `vuln/helm-no-netpol`
- **Bramka:** job `IaC (Checkov)` (CKV2_K8S_6); weryfikacja w klastrze — etap 14.
- **Co psujemy:** `networkPolicy.enabled: false` — brak polityk default-deny; każdy pod w klastrze ma dostęp do bazy i aplikacji (z pominięciem Traefika), aplikacja ma nieograniczony ruch wychodzący (CWE-923).
- **Poprawka w `main`:** `networkPolicy.enabled: true` — default-deny; aplikacja przyjmuje ruch tylko z Traefika, baza tylko z aplikacji, ruch wychodzący aplikacji tylko do bazy i DNS (zweryfikowane w k3d w etapie 6).
