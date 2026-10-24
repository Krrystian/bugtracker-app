# Wyniki testów akceptacyjnych

| Test | Status | Data |
|---|---|---|
| T1 Blokada i raportowanie podatności kodu (SAST/SCA) | ✅ zaliczony | 2026-10-24 |
| T2 Centralizacja raportów (SARIF) | ✅ zaliczony | 2026-10-24 |
| T3 Integralność i weryfikacja podpisów Cosign | ⏳ etap 14 | — |
| T4 Brama wdrożeniowa | ✅ zaliczony | 2026-10-24 |
| T5 Szczelność sekretów | ⏳ etap 12 | — |

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
