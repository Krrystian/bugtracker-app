# Wyniki skanerów bezpieczeństwa

Raporty wszystkich skanerów trafiają w formacie SARIF do **Security → Code scanning** repozytorium (kategoria = nazwa skanera). Bramka `scripts/sarif-gate.py` przerywa job, gdy jest choć jedno znalezisko High/Critical (poziom `error` lub `security-severity` ≥ 7.0); znaleziska niższej wagi są tylko raportowane.

| Podetap | Skaner | Rodzaj | `main` | Branch demonstracyjny |
|---|---|---|---|---|
| 11a | Semgrep 1.180.0 | SAST | ✅ 0 znalezisk | `vuln/sast-code` ❌ (2× High, 1× Medium) |
| 11b | OSV-Scanner 2.6.0 | SCA | ✅ 0 znalezisk | `vuln/sca-deps` ❌ ([run 40075903495](https://github.com/Krrystian/bugtracker-app/actions/runs/40075903495), critical CVE-2018-20060) — test T1 |
| 11c | Checkov 3.3.26 | IaC (Helm/K8s) | ✅ 0 błędów (458 testów, 5 udokumentowanych wyjątków) | `vuln/helm-privileged` ❌ ([run 40078615628](https://github.com/Krrystian/bugtracker-app/actions/runs/40078615628), 15× High), `vuln/helm-no-netpol` ❌ ([run 40078821444](https://github.com/Krrystian/bugtracker-app/actions/runs/40078821444), CKV2_K8S_6) |
| 11d | Syft 1.54.1 | SBOM (CycloneDX) | artefakt `sbom-cyclonedx` (137 komponentów) | n/d — inwentarz, nie bramka |
| 11e | OWASP ZAP 2.17 (`20261008`) | DAST (baseline) + polityka `.zap/rules.tsv` | ✅ 0 naruszeń polityki (58 reguł OK) | `vuln/dast-runtime` ❌ ([run 40088388516](https://github.com/Krrystian/bugtracker-app/actions/runs/40088388516), 4 reguły FAIL, 17 wystąpień) |
| 11f | Gitleaks 8.30.1 | sekrety w kodzie i historii git | ✅ 0 wycieków | `vuln/secret-leak` ❌ ([run 40092751830](https://github.com/Krrystian/bugtracker-app/actions/runs/40092751830), critical `generic-api-key`) |
| 11g | Hadolint 2.15.1 + polityka `.hadolint.yaml` | lint Dockerfile | ✅ 0 uwag | `vuln/dockerfile-bad-practices` *(po scaleniu)* |

## 11a: Semgrep (SAST)

**Czym jest SAST:** analiza statyczna kodu źródłowego, bez uruchamiania aplikacji. Skaner szuka wzorców typowych błędów: sklejania SQL z danymi użytkownika, wyłączonego escapowania HTML, słabej kryptografii, sekretów w kodzie.

**Konfiguracja:** zestawy reguł `p/python`, `p/owasp-top-ten`, `p/jwt` (564 reguły) + reguły projektu `.semgrep/rules.yml`; `--exclude=Dockerfile` — Dockerfile należy do joba Hadolint (decyzja 2026-10-24: `p/owasp-top-ten` zawiera regułę `last-user-is-root`, identyczną z blokującą DL3002 Hadolinta; jeden problem = jedna bramka) (XSS w szablonach Jinja2, `Markup()` na zmiennych; publiczne zestawy nie obejmują szablonów renderowanych przez FastAPI).

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

**Wyniki `vuln/sca-deps` (2026-10-24):** pada wyłącznie `SCA (OSV-Scanner)` na kroku bramki; 48 alertów, najpoważniejszy critical CVE-2018-20060 w `urllib3@1.22`. Szczegóły: `docs/test-results.md` (T1).

## 11c: Checkov (IaC — Helm i Kubernetes)

**Czym jest skan IaC:** sprawdza nie kod aplikacji, tylko **konfigurację wdrożenia** (Infrastructure as Code): czy kontener działa jako root lub `privileged`, czy ma limity zasobów, czy system plików jest tylko do odczytu, czy jest NetworkPolicy, czy obraz ma przypiętą wersję itd.

**Zakres:** wykres `charts/bugtracker` (framework `helm`: Checkov sam renderuje wykres z `image.tag` = commit, namespace przez `HELM_NAMESPACE`; znaleziska mapowane na pliki `templates/`) + manifesty `k8s/` i `infra/` (framework `kubernetes`).

**Pierwszy skan `main` i decyzje:**

| Check | Znaczenie | Decyzja |
|---|---|---|
| CKV_K8S_21 | zasoby w namespace `default` | fałszywy alarm renderowania → `namespace: {{ .Release.Namespace }}` w szablonach + `HELM_NAMESPACE` |
| CKV_K8S_35 | sekrety jako zmienne środowiskowe | **poprawione**: sekrety montowane jako pliki (`/run/secrets/bugtracker`, tryb 0440), aplikacja czyta je przez `SECRETS_DIR`, PostgreSQL przez `POSTGRES_PASSWORD_FILE` |
| CKV_K8S_15 | `imagePullPolicy` ≠ `Always` | **poprawione** w wykresie; w `k8s/` wyjątek (lokalny obraz Docker Desktop) |
| CKV2_K8S_6 | pody bez NetworkPolicy (`k8s/`) | **poprawione**: `k8s/networkpolicy.yaml` (te same reguły co wykres) |
| CKV_K8S_43 | obraz bez digestu | wyjątek: tag = niezmienny SHA commita; digest i podpis wymusza Kyverno (etap 14) |
| CKV_K8S_40 | niski UID (PostgreSQL 70) | wyjątek: użytkownik `postgres` oficjalnego obrazu, non-root wymuszony (`runAsNonRoot`, PSA restricted); zmiana UID psuje własność danych na PVC |

Wyjątki są adnotacjami `checkov.io/skip*` przy konkretnym zasobie, z uzasadnieniem; w raporcie widoczne jako pominięte (nie blokują). Żadna reguła nie jest wyłączona globalnie.

**Pułapka znaleziona przy wdrażaniu:** gdy Checkov nie potrafi wyrenderować wykresu (np. brak pliku values), wypisuje tylko ostrzeżenie i kończy sukcesem — wykres nie byłby sprawdzony. Krok CI zamienia to na błąd (`Failed processing helm chart` lub brak „helm scan results” → `exit 1`).

Po zmianach: `helm` 184 ✅ / 0 ❌ / 2 wyjątki, `kubernetes` 274 ✅ / 0 ❌ / 3 wyjątki. Test na wykresie z `privileged: true` i `runAsUser: 0`: 8 znalezisk High (CKV_K8S_16, 20, 22, 23, 40) → bramka `exit 1`.

**Wyniki branchy demonstracyjnych (2026-10-24):** w obu pada wyłącznie `IaC (Checkov)` na kroku bramki; `Unit tests`, `SAST (Semgrep)`, `SCA (OSV-Scanner)`, `Build image` zielone, publikacja pominięta.

| Branch | Najważniejsze alerty (plik `charts/bugtracker/templates/…`) | Realne ryzyko |
|---|---|---|
| `vuln/helm-privileged` | CKV_K8S_16 privileged, CKV_K8S_23 root, CKV_K8S_20 allowPrivilegeEscalation, CKV_K8S_22 zapisywalny root FS, CKV_K8S_28/37 capabilities (NET_RAW), CKV_K8S_31 seccomp, CKV_K8S_11/13 brak limitów CPU/RAM — `deployment.yaml`, `postgres-deployment.yaml` | **tak**: przejęcie kontenera `privileged` = przejęcie węzła (dostęp do urządzeń i jądra hosta); brak limitów pozwala jednemu podowi zagłodzić węzeł |
| `vuln/helm-no-netpol` | CKV2_K8S_6 pody bez NetworkPolicy — `deployment.yaml`, `postgres-deployment.yaml` | **tak**: każdy pod w klastrze może łączyć się bezpośrednio z bazą; przejęta aplikacja może wysyłać dane dokądkolwiek |

**Wyjątki w GitHub Security:** SARIF Checkova oznacza pominięte checki polem `suppressions` (z uzasadnieniem), ale GitHub pokazuje je jako otwarte alerty. 5 alertów (CKV_K8S_43 ×2, CKV_K8S_40 ×2, CKV_K8S_15) zamknięto ręcznie w GitHub jako *won't fix* z tym samym uzasadnieniem (decyzja właściciela projektu). Na `main`: 0 otwartych alertów.

## 11d: SBOM (CycloneDX)

**Czym jest SBOM:** *Software Bill of Materials* — spis wszystkich składników obrazu (pakiety systemu i biblioteki), z wersjami, licencjami i identyfikatorami `purl`. Nie jest bramką: to inwentarz, dzięki któremu po ogłoszeniu nowej podatności (np. w `openssl`) od razu wiadomo, które obrazy ją zawierają, bez ponownego skanowania. W etapie 14 SBOM jest podpisywany Cosignem jako *attestation* obrazu.

**Konfiguracja:** job `SBOM (CycloneDX)` — Syft 1.54.1 skanuje obraz `linux/amd64` zbudowany w jobie `Build image` (przekazany jako artefakt `image-amd64`); tylko pakiety (`SYFT_FILE_METADATA_SELECTION=none` — bez 2751 wpisów pojedynczych plików). Wynik: artefakt przebiegu **`sbom-cyclonedx`** (`sbom.cdx.json`, przechowywany 90 dni) + podsumowanie w zakładce przebiegu. `Push to Docker Hub` wymaga istnienia SBOM.

**Zawartość (obraz z `main`, lokalnie):** CycloneDX 1.7, **137 komponentów**: 87 pakietów Debiana (`pkg:deb/...`, np. `openssl 3.5.7-1~deb13u3`), 36 bibliotek Pythona (`pkg:pypi/...`, np. `fastapi 0.159.0` MIT), interpreter `python 3.12.15`, system `debian 13`.

## 11e: OWASP ZAP (DAST)

**Czym jest DAST:** *Dynamic Application Security Testing* — test **działającej** aplikacji z zewnątrz, przez HTTP, bez dostępu do kodu. Wykrywa to, czego nie widać w kodzie ani w konfiguracji: brakujące nagłówki bezpieczeństwa, niebezpieczne flagi ciasteczek, ujawnianie informacji w odpowiedziach serwera, błędne przekierowania.

**Konfiguracja:** job `DAST (OWASP ZAP)` (zależy od `Build image` i `IaC (Checkov)` — wykres jest wdrażany dopiero po przejściu skanu IaC) uruchamia `scripts/dast-zap.sh`:

1. tymczasowy klaster k3d (v5.9.0, binarka weryfikowana SHA-256) z lokalnym rejestrem `dast-registry`,
2. obraz z bieżącego przebiegu (artefakt `image-amd64`) → push do lokalnego rejestru,
3. `helm install` wykresu `charts/bugtracker` (namespace z PSA `restricted`, jednorazowe losowe sekrety, Helm v4.3.0 weryfikowany SHA-256),
4. ZAP *baseline* (skan pasywny: pająk + ocena odpowiedzi) z kontenera w sieci klastra,
5. `scripts/zap-to-sarif.py` — konwersja JSON → SARIF (ZAP nie generuje SARIF): ryzyko High → `error` (blokuje), Medium → `warning`, Low/Informational → `note`,
6. SARIF → GitHub Security (kategoria `zap`), raport HTML/JSON jako artefakt `zap-report` (30 dni), bramka; klaster zawsze usuwany.

**Ustalenia przy wdrażaniu (lokalnie):** `--registry-create <nazwa>` nie dodaje przedrostka `k3d-` (nazwa w klastrze = `dast-registry:5050`); load balancer k3d przekazuje tylko porty podane w `--port` (bez tego brak dostępu do Traefika); przy błędzie skrypt wypisuje pody, zdarzenia i logi przed usunięciem klastra.

**Wynik `main` (lokalnie, obraz `e68c74c`):** 58 reguł bez uwag, 0 Low/Medium/High; 3 alerty *Informational* (wykryty formularz logowania, odpowiedzi z ciasteczkiem sesji, „Cookie Poisoning” — parametr formularza odbity w nazwie/wartości ciasteczka CSRF) — opisują działanie aplikacji, nie podatności. Nagłówki bezpieczeństwa (CSP, `X-Frame-Options`, `nosniff`), flagi ciasteczek (`HttpOnly`, `SameSite=Strict`) i brak ujawniania wersji — bez uwag.

**Polityka reguł ZAP (`.zap/rules.tsv`) — decyzja właściciela projektu (2026-10-24):** skan pasywny ZAP ocenia błędy konfiguracji odpowiedzi (nagłówki, ciasteczka) najwyżej jako *Medium*, więc ogólna bramka High/Critical nigdy by ich nie zatrzymała. Zamiast obniżać próg dla wszystkich alertów, projekt ma **jawną listę reguł, które blokują** (`FAIL`): brak CSP (10038), brak ochrony przed clickjackingiem (10020), brak `X-Content-Type-Options` (10021), ujawnianie wersji w `Server` (10036) i `X-Powered-By` (10037), ciasteczko bez `HttpOnly` (10010) i `SameSite` (10054), brak tokenów anty-CSRF (10202). `scripts/zap-to-sarif.py --policy` zgłasza je jako `error` / 8.0; pozostałe alerty ZAP są tylko raportowane. Celowo pominięto 10011 (ciasteczko bez `Secure`) — tymczasowy klaster DAST działa po HTTP; produkcyjnie `COOKIE_SECURE=true` za TLS. To jedyne odstępstwo od reguły High/Critical z CLAUDE.md i dotyczy tylko ZAP.

Wersja secure z polityką: `FAIL-NEW: 0`, 58 reguł OK → bramka przechodzi.

**Wynik `vuln/dast-runtime` (2026-10-24):** pada wyłącznie `DAST (OWASP ZAP)` na kroku bramki (25 znalezisk, 17 blokujących); `Unit tests`, Semgrep, OSV, Checkov, Build, SBOM zielone; publikacja pominięta. Alerty: 10038 brak CSP (×5), 10020 brak ochrony przed clickjackingiem (×3), 10021 brak `X-Content-Type-Options` (×4), 10036 wersja serwera w `Server` (×5). **Realne ryzyko — tak:** bez CSP wstrzyknięty skrypt wykona się w przeglądarce; bez `X-Frame-Options` stronę można osadzić w ramce obcej witryny i podstępem nakłonić użytkownika do kliknięć (clickjacking); ujawniona wersja ułatwia dobór gotowego exploita.

**Alerty informacyjne:** ZAP zgłasza też alerty *Informational* (np. „Authentication Request Identified”, „Session Management Response Identified”) — opisują działanie aplikacji, nie podatności. Od tej zmiany nie trafiają do SARIF (chyba że są w polityce), zostają w pełnym raporcie `zap-report`; wcześniej zaśmiecały GitHub Security na `main` (8 alertów *note*).

## 11f: Gitleaks (sekrety)

**Czym jest skan sekretów:** wyszukiwanie haseł, kluczy API, tokenów i kluczy prywatnych w kodzie **oraz w całej historii git**. Usunięcie sekretu w kolejnym commicie go nie unieważnia — stara wersja nadal jest w repozytorium (a w publicznym repo — w internecie); jedyna poprawka to unieważnienie i wymiana sekretu.

**Konfiguracja:** job `Secrets (Gitleaks)` — `checkout` z `fetch-depth: 0` (cała historia), Gitleaks 8.30.1 (przypięty digestem) w trybie `git`, `--redact` (wartości nie trafiają do logów ani raportu), kontener jako użytkownik runnera (git odrzuca repo innego właściciela), brak podsumowania skanu w logu = błąd narzędzia.

**Ustalenie przy wdrażaniu:** SARIF Gitleaksa **nie zawiera poziomu ważności** — bramka uznałaby wyciek za nieblokujący, a GitHub pokazałby go jako zwykłe ostrzeżenie. `scripts/sarif-set-severity.py` ustawia `error` / 9.0 (Critical) dla każdego znaleziska przed uploadem.

**Wynik `main`:** cała historia — 0 wycieków. Lokalny skan katalogu roboczego znalazł 2 wartości w `.env` (hasło bazy, klucz tokenów) — plik jest w `.gitignore` i nigdy nie był commitowany; w CI skanowana jest historia git, nie katalog lokalny.

**Wynik `vuln/secret-leak` (2026-10-24):** pada wyłącznie `Secrets (Gitleaks)` na kroku bramki; wszystkie pozostałe joby (łącznie z DAST) zielone, publikacja pominięta. Alert **critical** `generic-api-key` w `app/payments.py:8`. Wartość jest losowa i nie działa w żadnej usłudze; dzięki `--redact` nie ma jej w logach ani w raporcie. **Realne ryzyko — tak (dla prawdziwego klucza):** każdy, kto ma dostęp do repozytorium (tu: publicznego), może go użyć; usunięcie z kodu nie wystarcza — klucz trzeba unieważnić. Zewnętrzny GitGuardian nie zareagował — sprawdza tylko Pull Requesty, a branche `vuln/*` ich nie mają.

## 11g: Hadolint (Dockerfile)

**Czym jest lint Dockerfile:** sprawdzenie pliku budującego obraz pod kątem dobrych praktyk: przypięte wersje (obrazu bazowego, pakietów `apt`/`pip`), brak roota, `COPY` zamiast `ADD`, brak zbędnej pamięci podręcznej, `pipefail` w potokach; polecenia `RUN` dodatkowo sprawdza ShellCheck.

**Polityka `.hadolint.yaml` (spójnie z decyzją dla ZAP):** domyślnie Hadolint zgłasza większość złych praktyk jako *warning* — bramka by ich nie zatrzymała. Polityka podnosi do `error` (blokuje): DL3002 (ostatni `USER` = root), DL3006 (obraz bez tagu), DL3007 (`latest`), DL3008 / DL3013 (nieprzypięte `apt` / `pip`), DL3020 (`ADD`), DL3042 (cache `pip`), DL4006 (brak `pipefail`). Pozostałe uwagi są tylko raportowane.

**Architektura:** `Build image` zależy od Hadolinta — obraz nie jest budowany z Dockerfile, który nie przeszedł polityki (zatem SBOM i DAST też nie działają na takim obrazie).

**Wynik `main`:** 0 uwag. Test na celowo złym Dockerfile: 11 uwag, 7 blokujących.
