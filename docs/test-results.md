# Wyniki testów akceptacyjnych

| Test | Status | Data |
|---|---|---|
| T1 Blokada i raportowanie podatności kodu (SAST/SCA) | ✅ zaliczony | 2026-10-24 |
| T2 Centralizacja raportów (SARIF) | ✅ zaliczony | 2026-10-24 |
| T3 Integralność i weryfikacja podpisów Cosign | ✅ zaliczony | 2026-10-24 |
| T4 Brama wdrożeniowa | ✅ zaliczony | 2026-10-24 |
| T5 Szczelność sekretów | ✅ zaliczony | 2026-10-24 |

## T1 Blokada i raportowanie podatności kodu (SAST/SCA)

**Cel:** przestarzała biblioteka z krytyczną CVE (OSV.dev) przerywa pipeline, a w Security → Code scanning pojawia się raport wskazujący bibliotekę.

**Przebieg (2026-10-24):** push branchu `vuln/sca-deps` (VULN-04: `urllib3==1.22` w `requirements.in`, lock files zregenerowane `scripts/lock-deps.sh` — zmiana dokładnie o tę jedną linię).

**Dowód:** [przebieg 40075903495](https://github.com/Krrystian/bugtracker-app/actions/runs/40075903495)

| Job | Wynik |
|---|---|
| Unit tests | ✅ |
| SAST (Semgrep) | ✅ |
| **SCA (OSV-Scanner)** | ❌ — skan ✅, upload SARIF ✅, **krok „Security gate (High/Critical)” ❌** |
| Build image | ✅ |
| Push to Docker Hub / Notify GitOps repo | ⏭ pominięte — obraz **nie** trafił do Docker Hub |

Security → Code scanning (gałąź `vuln/sca-deps`, narzędzie `osv-scanner`): 48 alertów, w tym **critical CVE-2018-20060 — „Package 'urllib3@1.22' is vulnerable to 'CVE-2018-20060' (also known as 'PYSEC-2018-32', 'GHSA-www2-v7xj-xrc6')”** oraz alerty High dla tej samej biblioteki. Na `main`: 0 alertów osv-scanner.

**Wynik:** ✅ zaliczony.

## T2 Centralizacja raportów (SARIF)

**Cel:** push `vuln/helm-privileged` (kontener jako root) → Checkov generuje SARIF; wyniki skanerów statycznych i DAST widoczne we wspólnym panelu GitHub Security.

**Przebieg i dowody (2026-10-24):**

1. `vuln/helm-privileged` ([przebieg 40078615628](https://github.com/Krrystian/bugtracker-app/actions/runs/40078615628)): `IaC (Checkov)` ❌ (krok bramki), SARIF wysłany (`if: always()`); w Security → Code scanning (filtr `branch:vuln/helm-privileged`, narzędzie `checkov`) alerty m.in. **CKV_K8S_23 „Minimize the admission of root containers”** i CKV_K8S_16 „Container should not be privileged” wskazujące `charts/bugtracker/templates/deployment.yaml`.
2. Ten sam panel zawiera raporty wszystkich skanerów w jednym formacie SARIF — na `main` (przebieg [40085643395](https://github.com/Krrystian/bugtracker-app/actions/runs/40085643395)) analizy: **Semgrep OSS** (SAST), **osv-scanner** (SCA), **checkov** (IaC), **OWASP ZAP** (DAST, raport skonwertowany przez `scripts/zap-to-sarif.py`).

```bash
gh api 'repos/Krrystian/bugtracker-app/code-scanning/analyses?ref=refs/heads/main' --jq '[.[].tool.name] | unique'
# ["OWASP ZAP","Semgrep OSS","checkov","osv-scanner"]
```

Na `vuln/helm-privileged` job DAST jest pominięty zgodnie z architekturą (wykres o złej konfiguracji nie jest wdrażany, gdy Checkov go zablokował); wyniki DAST pochodzą z gałęzi, na których wykres przeszedł skan IaC (`main`, a demonstracyjnie `vuln/dast-runtime`).

**Wynik:** ✅ zaliczony.

## T4 Brama wdrożeniowa

**Cel:** po zielonym CI repozytorium aplikacji nowy tag obrazu trafia do repozytorium GitOps wyłącznie na gałąź `development`; działająca aplikacja nie zmienia się do ręcznego scalenia `development` → `main`.

**Przebieg (2026-10-24):**

1. Scalenie PR Krrystian/bugtracker-app#1 → commit `50c4eb5` na `main`.
2. CI repozytorium aplikacji ([przebieg 40072560307](https://github.com/Krrystian/bugtracker-app/actions/runs/40072560307)): Unit tests ✅ → Build image ✅ → Push to Docker Hub ✅ (`krys3x15/bugtracker:50c4eb5…`) → Notify GitOps repo ✅ (`repository_dispatch` `image-published`).
3. Workflow repozytorium GitOps ([przebieg 40072686137](https://github.com/Krrystian/bugtracker-gitops/actions/runs/40072686137), zdarzenie `repository_dispatch`): walidacja payloadu ✅, commit `11b5297` „deploy: bugtracker 50c4eb5” autorstwa `github-actions[bot]` **na `development`**.

**Dowód (stan po przebiegu):**

| Miejsce | `image.tag` |
|---|---|
| `bugtracker-gitops` @ `development` | `50c4eb544001af0d4fcd0dd6c83c040c057ad130` (nowy) |
| `bugtracker-gitops` @ `main` | `4945053f4d20c87210833ba192f1aef9b10468a3` (bez zmian) |
| klaster k3d (`deploy/bugtracker`) | `krys3x15/bugtracker:4945053…` (bez zmian), Argo CD Synced/Healthy |

Komendy:

```bash
git -C bugtracker-gitops show origin/development:environments/development/values.yaml | grep tag:
git -C bugtracker-gitops show origin/main:environments/development/values.yaml | grep tag:
kubectl -n bugtracker get deploy bugtracker -o jsonpath='{.spec.template.spec.containers[0].image}'
```

**Wynik:** ✅ zaliczony. Wdrożenie wymaga świadomej decyzji człowieka (PR `development` → `main` w repozytorium GitOps; `main` chroniony, także dla administratora).

## T5 Szczelność sekretów

**Cel:** nowy sekret zaszyfrowany `kubeseal` jako `SealedSecret` w publicznym repozytorium GitOps, wdrożony przez Argo CD → odszyfrowany w klastrze; jawna wartość nie występuje w logach ani w historii git.

**Przebieg (2026-10-24):**

1. Losowa wartość (48 znaków) dla sekretu `bugtracker-t5-demo` (klucz `api-token`) wygenerowana i od razu zaszyfrowana kluczem publicznym kontrolera Sealed Secrets v0.40.0 — nigdzie niezapisana ani niewypisana; do weryfikacji zachowany wyłącznie skrót SHA-256 (poza repo, usunięty po teście).
2. Plik `environments/development/secrets/bugtracker-t5-demo.sealedsecret.yaml` w [Krrystian/bugtracker-gitops#6](https://github.com/Krrystian/bugtracker-gitops/pull/6) — Gitleaks (wymagany check) przepuścił szyfrogram; PR scalony przez właściciela projektu.
3. Webhook → Argo CD (trzecie źródło `Application`: katalog `secrets/`) → `SealedSecret` w namespace `bugtracker` → kontroler utworzył `Secret` (ownerReference: `SealedSecret`, warunek `Synced=True`).

**Dowód:**

| Sprawdzenie | Wynik |
|---|---|
| Skrót SHA-256 wartości odszyfrowanej w klastrze = skrót wartości oryginalnej | ✅ identyczne |
| Wystąpienia wartości (jawnej i w base64) w historii git `bugtracker-gitops`, wszystkie gałęzie (26 commitów) | ✅ 0 |
| jw. w `bugtracker-app`, wszystkie gałęzie (60 commitów) | ✅ 0 |
| Logi `argocd-application-controller`, `argocd-repo-server`, `argocd-server`, `sealed-secrets-controller` (30 min) | ✅ 0 |
| Logi CI repozytorium GitOps (5 ostatnich przebiegów) | ✅ 0 |

Dodatkowo: `vuln/plaintext-secret` (jawny `Secret` w repo GitOps) zatrzymany przez Gitleaks ([przebieg 40099839420](https://github.com/Krrystian/bugtracker-gitops/actions/runs/40099839420), alert Critical), a do klastra nie trafił (Argo CD śledzi tylko `main`).

**Wynik:** ✅ zaliczony.

## Etap 13: testy bramek skanerów

**Kryteria (CLAUDE.md):** na każdym branchu `vuln/*` pipeline kończy się czerwono na zaplanowanym jobie, obraz **nie** jest publikowany w Docker Hub, brak dispatchu do GitOps, `main` zielony; bramka High/Critical (`exit 1`) dla Semgrep, OSV-Scanner, Checkov, Trivy, ZAP.

**Bramki:** każdy skaner wysyła SARIF do GitHub Security (`if: always()`), a krok *Security gate* (`scripts/sarif-gate.py`) kończy job `exit 1` przy znalezisku High/Critical (`level: error` lub `security-severity ≥ 7.0`). Uzupełnienia: polityki reguł ZAP (`.zap/rules.tsv`) i Hadolinta (`.hadolint.yaml`) — złe praktyki, które narzędzia domyślnie oceniają niżej, podniesione do poziomu blokującego; Gitleaks — każdy wyciek = Critical; Trivy — CVE z dostępną poprawką. Żaden skaner nie ma `continue-on-error` ani `exit-code: 0` bez bramki po nim.

**Weryfikacja (2026-10-24) na wszystkich przebiegach branchy `vuln/*`:**

| Branch | Commitów spoza `main` | Ich tagi w Docker Hub | Ich commity „deploy:” w GitOps | Przebiegów CI | `Push to Docker Hub` / `Notify GitOps repo` zakończone sukcesem | Czerwony job |
|---|---|---|---|---|---|---|
| `vuln/sast-code` | 2 | 0 | 0 | 2 | 0 | SAST (Semgrep) |
| `vuln/sca-deps` | 2 | 0 | 0 | 2 | 0 | SCA (OSV-Scanner) |
| `vuln/helm-privileged` | 2 | 0 | 0 | 2 | 0 | IaC (Checkov) |
| `vuln/helm-no-netpol` | 2 | 0 | 0 | 2 | 0 | IaC (Checkov) |
| `vuln/dast-runtime` | 2 | 0 | 0 | 2 | 0 | DAST (OWASP ZAP) |
| `vuln/secret-leak` | 2 | 0 | 0 | 2 | 0 | Secrets (Gitleaks) |
| `vuln/dockerfile-bad-practices` | 2 | 0 | 0 | 2 | 0 | Dockerfile (Hadolint) |
| `vuln/image-cve` | 1 | 0 | 0 | 1 | 0 | Image (Trivy) |

Metoda: commity branchy spoza `main` (`git rev-list origin/vuln/<x> --not origin/main`) porównane z pełną listą tagów `krys3x15/bugtracker` w Docker Hub (21 tagów, w tym 0 × `latest`) i ze skrótami SHA w commitach `deploy: bugtracker <sha>` na gałęzi `development` repo GitOps (15). **Kontrola pozytywna:** 20 z 21 tagów to dokładnie SHA commitów `main` (21. to tag `dcb8f64` sprzed przepisania historii — repozytorium archiwalne), więc metoda wykrywa opublikowane commity. `main` (`1ffd399`): 12/12 jobów zielonych.

Repo GitOps: `vuln/plaintext-secret` — `Secrets (Gitleaks)` ❌; Argo CD śledzi tylko `main`, sekret nie trafił do klastra.

Testy T1 i T2 (wymagane w etapie 13) — zaliczone, opisane wyżej.

**Wynik:** ✅ etap 13 zaliczony.

## T3 Integralność i weryfikacja podpisów Cosign

**Cel:** w repozytorium GitOps podmiana obrazu w `values.yaml` na losowy, niepodpisany (`vuln/unsigned-image`), wdrożenie w piaskownicy → Kyverno blokuje pod z błędem braku podpisu.

**Mechanizm:**
- CI (tylko `main`): obraz podpisany **po digeście** (`cosign sign`), SBOM CycloneDX dołączony jako podpisana atestacja (`cosign attest`), oba zweryfikowane kluczem `cosign.pub` w tym samym jobie.
- Klaster: Kyverno v1.19.1, `ImageValidatingPolicy verify-bugtracker-images` (`infra/kyverno/verify-images.yaml`), `Deny`, namespace'y `bugtracker` i `sandbox`: obraz musi mieć podpis **i** podpisaną atestację SBOM kluczem projektu; tag zamieniany na digest; jedyny wyjątek — PostgreSQL przypięty digestem.

**Przebieg (2026-10-24):**

1. Gałąź `vuln/unsigned-image` w [bugtracker-gitops](https://github.com/Krrystian/bugtracker-gitops): `image: docker.io/library/nginx:1.27.3-alpine` (VULN-09).
2. `Application bugtracker-sandbox` (namespace `sandbox`, ręczna synchronizacja, bez Ingress i bazy) — synchronizacja: Deployment utworzony.
3. Kyverno odrzucił tworzenie poda:

```
ReplicaSet/bugtracker-6557cd966b: Error creating: admission webhook
"ivpol.validate.kyverno.svc-fail-finegrained-verify-bugtracker-images" denied the request:
Policy verify-bugtracker-images failed: image is not signed with the project Cosign key (cosign.pub)
```

Liczba podów w `sandbox`: 0.

**Kontrola pozytywna (produkcja, ta sama polityka w trybie `Deny`):** `rollout restart deploy/bugtracker` — nowe pody przyjęte z obrazem `docker.io/krys3x15/bugtracker:1d205e6…@sha256:fb2464faac3be55123ba200bda75013038f915ef15564ee9d2dabb9905cf3fa3` (digest dopisany przez Kyverno), aplikacja dostępna. Lokalnie: `cosign verify --key cosign.pub docker.io/krys3x15/bugtracker@sha256:fb2464faac3be55123ba200bda75013038f915ef15564ee9d2dabb9905cf3fa3` — podpis zweryfikowany kluczem publicznym, wpis w logu przejrzystości potwierdzony; `cosign verify-attestation --type cyclonedx` — OK.

**Ustalenia przy wdrażaniu:**
- `kyverno.io/v1 ClusterPolicy` (`verifyImages`) nie odczytuje podpisów cosign v3 (OCI referrers / Sigstore bundle) — „no signatures found” także dla podpisanego obrazu; przejście na `ImageValidatingPolicy` (sprawdzone na kopii polityki w trybie dry-run przed włączeniem blokady).
- Kyverno domyślnie mutował też Deployment (autogen) → Argo CD stale OutOfSync; autogen wyłączony — weryfikowane i mutowane są tylko Pody.
- Anonimowe zapytania Kyverno do Docker Hub trafiły na limit pobrań (`TOOMANYREQUESTS`), przez co przy `failurePolicy: Fail` nie dało się utworzyć nowych podów (produkcja działała na istniejących, restart cofnięty); Kyverno używa teraz tokenu Docker Hub tylko do odczytu (sekret `dockerhub-readonly` w namespace `kyverno`, poza Git).

**Wynik:** ✅ zaliczony.
