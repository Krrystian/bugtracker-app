# Podatności na gałęziach `vuln/*`

Każda podatność jest na osobnej gałęzi `vuln/<nazwa>`, która nigdy nie trafia do `main`. Gałąź psuje jedną rzecz i powinien ją zatrzymać jeden konkretny skaner. W kodzie podatne miejsca mają komentarz `VULN-XX`.

| ID | Gałąź | Co ją zatrzymuje |
|---|---|---|
| VULN-01 | `vuln/secret-leak` | Gitleaks |
| VULN-02 | `vuln/dockerfile-bad-practices` | Hadolint |
| VULN-03 | `vuln/sast-code` | Semgrep |
| VULN-04 | `vuln/sca-deps` | OSV-Scanner |
| VULN-05 | `vuln/image-cve` | Trivy |
| VULN-06 | `vuln/helm-privileged` | Checkov |
| VULN-07 | `vuln/helm-no-netpol` | Checkov |
| VULN-08 | `vuln/dast-runtime` | OWASP ZAP |
| VULN-09 | `vuln/unsigned-image` (repo GitOps) | Kyverno w klastrze |
| VULN-10 | `vuln/plaintext-secret` (repo GitOps) | Gitleaks w repo GitOps |
| VULN-11 | `vuln/helm-hostpath` | Checkov |

## VULN-01: klucz API w kodzie

W `app/payments.py` wpisany jest na sztywno klucz API. Wartość jest losowa i nie działa nigdzie. Gitleaks wykrywa go jako `generic-api-key`.

W `main` nie ma żadnych haseł ani kluczy w kodzie. Wszystko przychodzi ze zmiennych środowiskowych albo z sekretów Kubernetes.

## VULN-02: złe praktyki w Dockerfile

Dockerfile używa `python:latest`, instaluje pakiety bez przypiętych wersji, uruchamia skrypt pobrany z internetu (`curl | python`) i działa jako root. Hadolint to blokuje, więc obraz w ogóle się nie buduje.

W `main` obraz bazowy jest przypięty do wersji i digestu, a kontener działa jako zwykły użytkownik (UID 10001).

## VULN-03: podatny kod (SQL injection, XSS, MD5)

Nowa strona wyszukiwania `/ui/search` ma trzy błędy:
- parametr `q` jest doklejany do zapytania SQL (SQL injection),
- wynik jest wyświetlany bez escapowania HTML (XSS),
- zapytanie jest hashowane MD5 (słaby algorytm).

Semgrep blokuje dwa pierwsze, MD5 tylko zgłasza. W `main` zapytania idą przez ORM, szablony mają włączone escapowanie, a hasła są hashowane Argon2.

## VULN-04: stara biblioteka z krytyczną podatnością

Do zależności dodana jest biblioteka `urllib3==1.22` z 2017 roku. Ma podatność CVE-2018-20060 (Critical, 9.8): przy przekierowaniu na inny serwer wysyła dalej dane logowania. OSV-Scanner to wykrywa (test T1).

W `main` tej biblioteki nie ma, a wszystkie zależności są przypięte w plikach `requirements*.txt` i sprawdzane przy każdym PR.

## VULN-05: stary obraz bazowy

Obraz bazowy to `python:3.12.0-slim-bookworm` z 2023 roku, czyli Debian 12 bez dwóch lat poprawek. Trivy znajduje około 90 podatności High/Critical, które mają już poprawkę.

W `main` jest aktualny obraz `python:3.12.16-slim-trixie`.

## VULN-06: kontener jako root i `privileged`

W `values.yaml` wykresu Helm kontenery działają jako root, mają `privileged: true`, mogą podnosić uprawnienia i nie mają limitów CPU ani pamięci. Checkov zgłasza 15 problemów High (test T2).

W `main` kontenery działają bez roota, z systemem plików tylko do odczytu, bez dodatkowych uprawnień i z limitami.

## VULN-07: brak NetworkPolicy

`networkPolicy.enabled: false`, więc każdy pod w klastrze może połączyć się z bazą i aplikacją. Checkov zgłasza brak NetworkPolicy.

W `main` domyślnie wszystko jest zablokowane: aplikacja przyjmuje ruch tylko z Traefika, a baza tylko z aplikacji.

## VULN-08: proxy usuwa nagłówki bezpieczeństwa

Middleware Traefika usuwa nagłówki ustawiane przez aplikację (CSP, `X-Frame-Options`, `X-Content-Type-Options`) i dodaje nagłówek `Server` z wersją oprogramowania. W kodzie wszystko jest w porządku, błąd widać dopiero na działającej aplikacji, dlatego łapie go OWASP ZAP.

W `main` tego middleware nie ma, a aplikacja ustawia wszystkie nagłówki sama.

## VULN-09: niepodpisany obraz w repo GitOps

W `values.yaml` repo GitOps zamiast naszego obrazu wpisany jest `nginx:1.27.3-alpine`. Symuluje to podmianę obrazu przez kogoś z zewnątrz. Gałąź jest wdrażana tylko w piaskownicy (namespace `sandbox`). Kyverno odrzuca pod z komunikatem „image is not signed with the project Cosign key” (test T3).

W `main` wdrażane są tylko obrazy z CI podpisane kluczem projektu.

## VULN-10: jawne hasło w repo GitOps

Plik `db-admin.secret.yaml` to zwykły `Secret` z hasłem zapisanym jawnym tekstem (hasło jest losowe i nieużywane). Gitleaks w repo GitOps to wykrywa ([przebieg](https://github.com/Krrystian/bugtracker-gitops/actions/runs/40099839420)). Plik nie trafia do klastra, bo Argo CD wdraża tylko `main`.

W `main` sekrety są tylko w postaci zaszyfrowanej (`SealedSecret`).

## VULN-11: dostęp do gniazda Dockera

Kontener aplikacji ma zamontowany `/var/run/docker.sock` z węzła. Kto przejmie aplikację, może sterować kontenerami na węźle i wydostać się z kontenera. Checkov blokuje to regułą CKV_K8S_27 ([przebieg](https://github.com/Krrystian/bugtracker-app/actions/runs/42366684999)). Nawet bez Checkova taki pod nie zostałby przyjęty w namespace `bugtracker`, bo Pod Security `restricted` zabrania `hostPath`.

W `main` pod nie ma żadnych wolumenów z węzła.
