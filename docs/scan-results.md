# Wyniki skanerów bezpieczeństwa

Raporty wszystkich skanerów trafiają w formacie SARIF do **Security → Code scanning** repozytorium (kategoria = nazwa skanera). Bramka `scripts/sarif-gate.py` przerywa job, gdy jest choć jedno znalezisko High/Critical (poziom `error` lub `security-severity` ≥ 7.0); znaleziska niższej wagi są tylko raportowane.

| Podetap | Skaner | Rodzaj | `main` | Branch demonstracyjny |
|---|---|---|---|---|
| 11a | Semgrep 1.180.0 | SAST | ✅ 0 znalezisk | `vuln/sast-code` ❌ (2× High, 1× Medium) |
| 11b | OSV-Scanner 2.6.0 | SCA | ✅ 0 znalezisk | `vuln/sca-deps` *(po scaleniu)* |

## 11a: Semgrep (SAST)

**Czym jest SAST:** analiza statyczna kodu źródłowego, bez uruchamiania aplikacji. Skaner szuka wzorców typowych błędów: sklejania SQL z danymi użytkownika, wyłączonego escapowania HTML, słabej kryptografii, sekretów w kodzie.

**Konfiguracja:** zestawy reguł `p/python`, `p/owasp-top-ten`, `p/jwt` (564 reguły) + reguły projektu `.semgrep/rules.yml` (XSS w szablonach Jinja2, `Markup()` na zmiennych; publiczne zestawy nie obejmują szablonów renderowanych przez FastAPI).

**Wyniki (2026-10-24):**

| Gałąź | Przebieg | Wynik joba | Znaleziska |
|---|---|---|---|
| `main` | [8f84a57](https://github.com/Krrystian/bugtracker-app/commit/8f84a57) | ✅ | 0 („Ran 211 rules on 54 files: 0 findings”) |
| `vuln/sast-code` | [run 40074900580](https://github.com/Krrystian/bugtracker-app/actions/runs/40074900580) | ❌ krok *Security gate* | 3 (poniżej) |

Na `vuln/sast-code` pozostałe joby: `Unit tests` ✅, `Build image` ✅, `Push to Docker Hub` / `Notify GitOps repo` pominięte (obraz nie został opublikowany).

| Alert | Reguła | Miejsce | Waga | Realne ryzyko? |
|---|---|---|---|---|
| SQL injection | `avoid-sqlalchemy-text` | `app/web.py:299` | error → **blokuje** | **tak**: `q=' OR '1'='1` zwraca wszystkie rekordy, sprytniejsze ciągi czytają inne tabele (`UNION SELECT ... FROM users`) |
| XSS | `jinja2-autoescape-disabled-in-template` | `app/templates/search.html:11` | error → **blokuje** | **tak**: `q=<script>...</script>` trafia do HTML bez escapowania (w `main` dodatkowo zablokowałoby to CSP) |
| MD5 | `insecure-hash-algorithm-md5` | `app/web.py:301` | warning → raport | **niskie** w tym miejscu (odcisk zapytania, nie hasło), ale w kontekście haseł/podpisów byłoby krytyczne |

## 11b: OSV-Scanner (SCA)

**Czym jest SCA:** analiza składu oprogramowania — skaner nie czyta naszego kodu, tylko **listę bibliotek z wersjami** i porównuje ją z bazą znanych podatności (OSV.dev: CVE, GHSA, PYSEC). Większość kodu aplikacji to cudze biblioteki, więc dziura w bibliotece to dziura w aplikacji.

**Ustalenie przy wdrażaniu (fałszywe alarmy):** pierwszy skan `main` zgłosił m.in. `anyio 4.9.0` (CVSS 9.3) i `h11 0.9.0` (CVSS 9.1). Tych wersji **nie było w obrazie** (faktycznie `anyio 4.15.1`, `h11 0.16.0` — już poprawione): `requirements.txt` przypinał tylko 10 bibliotek bezpośrednich, a OSV-Scanner „zgadywał” wersje 24 zależności przechodnich. Poprawka:

- `requirements.in` / `requirements-dev.in` — biblioteki bezpośrednie (edytowane ręcznie),
- `requirements.txt` (34 pakiety) / `requirements-dev.txt` (42) — **pełne lock files** generowane `scripts/lock-deps.sh` w tym samym obrazie Pythona co `Dockerfile`,
- skan z `--no-resolve` → skaner widzi dokładnie to, co trafia do obrazu; buildy są powtarzalne.

Po zmianie: `main` — 76 pakietów, **0 podatności**.

**Bramka:** SARIF z OSV-Scanner zawiera `security-severity` (CVSS) każdej podatności; `scripts/sarif-gate.py` blokuje od 7.0 (High).
