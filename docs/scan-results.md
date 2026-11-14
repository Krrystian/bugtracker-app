# Wyniki skanerów

Każdy skaner wysyła raport (w formacie SARIF) do zakładki **Security → Code scanning**. Skrypt `scripts/sarif-gate.py` przerywa job, jeśli znajdzie choć jeden problem o wadze High lub Critical. Słabsze problemy są tylko zgłaszane.

Na `main` wszystkie skanery przechodzą bez błędów. Każda gałąź `vuln/*` pada tylko na swoim skanerze, a obraz z niej nie jest publikowany.

| Gałąź | Skaner, który ją zatrzymał |
|---|---|
| `vuln/sast-code` | Semgrep |
| `vuln/sca-deps` | OSV-Scanner |
| `vuln/helm-privileged` | Checkov |
| `vuln/helm-no-netpol` | Checkov |
| `vuln/helm-hostpath` | Checkov |
| `vuln/dast-runtime` | OWASP ZAP |
| `vuln/secret-leak` | Gitleaks |
| `vuln/dockerfile-bad-practices` | Hadolint |
| `vuln/image-cve` | Trivy |

## Kolejność jobów

```
Unit tests ─┐
Hadolint ───┴─► Build image ─┬─► SBOM ───────────────┐
                             ├─► Trivy ──────────────┤
Checkov ─────────────────────┴─► DAST (ZAP) ─────────┤
Semgrep, OSV-Scanner, Gitleaks (niezależne) ─────────┴─► Push to Docker Hub ─► Notify GitOps (tylko main)
```

Skanery kodu działają równolegle, więc błąd jednego nie ukrywa wyników pozostałych. Obraz nie jest budowany, jeśli Dockerfile nie przeszedł Hadolinta, a aplikacja nie jest uruchamiana do testów ZAP, jeśli konfiguracja nie przeszła Checkova.

## Semgrep (analiza kodu, SAST)

Czyta kod źródłowy i szuka typowych błędów: sklejania SQL z danymi od użytkownika, wyłączonego escapowania HTML, słabej kryptografii. Używa publicznych zestawów reguł (`p/python`, `p/owasp-top-ten`, `p/jwt`) i własnych reguł z `.semgrep/rules.yml`, które sprawdzają szablony Jinja2.

Na `vuln/sast-code` ([przebieg](https://github.com/Krrystian/bugtracker-app/actions/runs/40074900580)) wykrył:
- SQL injection w `app/web.py`: `q=' OR '1'='1` zwraca wszystkie rekordy,
- XSS w `app/templates/search.html`: skrypt z parametru trafia na stronę,
- MD5 w `app/web.py`: tylko zgłoszone, bo w tym miejscu nie chroni niczego ważnego.

## OSV-Scanner (zależności, SCA)

Nie czyta naszego kodu, tylko listę bibliotek z wersjami, i sprawdza ją w bazie znanych podatności OSV.dev.

Pierwszy skan zgłaszał fałszywe alarmy, bo `requirements.txt` przypinał tylko biblioteki bezpośrednie, a skaner zgadywał wersje pozostałych. Teraz są dwa pliki: `requirements.in` z listą bibliotek i `requirements.txt` z pełną listą wszystkich pakietów i ich wersji, generowaną skryptem `scripts/lock-deps.sh`. Skaner widzi dokładnie to, co trafia do obrazu.

Na `vuln/sca-deps` ([przebieg](https://github.com/Krrystian/bugtracker-app/actions/runs/40075903495)) wykrył `urllib3 1.22` z krytyczną podatnością CVE-2018-20060.

## Checkov (konfiguracja Kubernetes i Helm)

Sprawdza konfigurację wdrożenia: czy kontener działa jako root, czy ma limity, czy system plików jest tylko do odczytu, czy jest NetworkPolicy. Skanuje wykres `charts/bugtracker` i manifesty w `k8s/` i `infra/`.

Kilka uwag uznaliśmy za wyjątki i opisaliśmy adnotacją przy konkretnym zasobie, np. PostgreSQL działa z UID 70, bo tak ma oficjalny obraz. Żadna reguła nie jest wyłączona dla całego projektu.

Jedna pułapka: gdy Checkov nie umie wyrenderować wykresu, kończy się sukcesem i niczego nie sprawdza. W CI jest dodatkowy krok, który traktuje to jako błąd.

Na `vuln/helm-privileged` ([przebieg](https://github.com/Krrystian/bugtracker-app/actions/runs/40078615628)) wykrył root, `privileged` i brak limitów, a na `vuln/helm-no-netpol` ([przebieg](https://github.com/Krrystian/bugtracker-app/actions/runs/40078821444)) brak NetworkPolicy.

## SBOM (CycloneDX)

SBOM to spis wszystkich składników obrazu: pakietów systemu i bibliotek Pythona z wersjami. Nie blokuje niczego, ale gdy pojawi się nowa podatność, od razu widać, które obrazy ją zawierają. Generuje go Syft, zapisuje się jako artefakt `sbom-cyclonedx` przebiegu i jest podpisywany Cosignem razem z obrazem.

## OWASP ZAP (test działającej aplikacji, DAST)

Testuje działającą aplikację z zewnątrz, przez HTTP. Wykrywa rzeczy, których nie widać w kodzie: brakujące nagłówki bezpieczeństwa, złe ustawienia ciasteczek, ujawnianie wersji serwera.

W CI skrypt `scripts/dast-zap.sh` stawia tymczasowy klaster k3d, wdraża w nim aplikację wykresem Helm, uruchamia ZAP, a na koniec usuwa klaster. ZAP nie generuje SARIF, więc `scripts/zap-to-sarif.py` zamienia jego raport.

ZAP ocenia brak nagłówków najwyżej jako Medium, więc zwykła bramka High/Critical by go nie zatrzymała. Dlatego w `.zap/rules.tsv` jest lista reguł, które zawsze blokują: brak CSP, brak ochrony przed osadzeniem w ramce, brak `X-Content-Type-Options`, ujawnienie wersji serwera, ciasteczka bez `HttpOnly` i `SameSite`, brak tokenów CSRF.

Na `vuln/dast-runtime` ([przebieg](https://github.com/Krrystian/bugtracker-app/actions/runs/40088388516)) wykrył brak CSP, brak ochrony przed ramką, brak `X-Content-Type-Options` i wersję serwera w nagłówku.

## Gitleaks (sekrety)

Szuka haseł, kluczy i tokenów w kodzie i w całej historii git. Usunięcie sekretu w kolejnym commicie nic nie daje, bo stara wersja zostaje w historii, więc taki sekret trzeba unieważnić.

Raport Gitleaksa nie ma wagi problemów, więc `scripts/sarif-set-severity.py` oznacza każdy wyciek jako Critical. Wartości są ukrywane w logach (`--redact`).

Na `vuln/secret-leak` ([przebieg](https://github.com/Krrystian/bugtracker-app/actions/runs/40092751830)) wykrył klucz API w `app/payments.py`.

## Hadolint (Dockerfile)

Sprawdza Dockerfile: przypięte wersje obrazu i pakietów, brak roota, `pipefail` w potokach. Domyślnie większość błędów zgłasza tylko jako ostrzeżenia, dlatego `.hadolint.yaml` podnosi najważniejsze z nich do poziomu blokującego.

Na `vuln/dockerfile-bad-practices` ([przebieg](https://github.com/Krrystian/bugtracker-app/actions/runs/40096588165)) wykrył `latest`, nieprzypięte pakiety, `curl | python` bez `pipefail` i `USER root`. Obraz nie został zbudowany.

## Trivy (obraz)

Sprawdza pakiety systemu w gotowym obrazie (np. `openssl`, `zlib`). Biblioteki Pythona sprawdza OSV-Scanner, więc Trivy patrzy tylko na system.

Blokuje tylko podatności, które mają już poprawkę (`--ignore-unfixed`). Debian ma zawsze sporo zgłoszonych podatności bez poprawki i bramka na nie blokowałaby `main` bez możliwości naprawy. Pełna lista jest w artefakcie `trivy-report`.

Na `vuln/image-cve` ([przebieg](https://github.com/Krrystian/bugtracker-app/actions/runs/40097682621)) wykrył około 90 podatności High/Critical w starym obrazie bazowym.
