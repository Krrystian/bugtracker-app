# Wyniki skanerów bezpieczeństwa

Raporty wszystkich skanerów trafiają w formacie SARIF do **Security → Code scanning** repozytorium (kategoria = nazwa skanera). Bramka `scripts/sarif-gate.py` przerywa job, gdy jest choć jedno znalezisko High/Critical (poziom `error` lub `security-severity` ≥ 7.0); znaleziska niższej wagi są tylko raportowane.

| Podetap | Skaner | Rodzaj | `main` | Branch demonstracyjny |
|---|---|---|---|---|
| 11a | Semgrep 1.180.0 | SAST | *(uzupełniane po przebiegu)* | `vuln/sast-code` |

## 11a: Semgrep (SAST)

**Czym jest SAST:** analiza statyczna kodu źródłowego, bez uruchamiania aplikacji. Skaner szuka wzorców typowych błędów: sklejania SQL z danymi użytkownika, wyłączonego escapowania HTML, słabej kryptografii, sekretów w kodzie.

**Konfiguracja:** zestawy reguł `p/python`, `p/owasp-top-ten`, `p/jwt` (564 reguły) + reguły projektu `.semgrep/rules.yml` (XSS w szablonach Jinja2, `Markup()` na zmiennych; publiczne zestawy nie obejmują szablonów renderowanych przez FastAPI).

*(wyniki i linki do przebiegów uzupełniane po pierwszych przebiegach CI)*
