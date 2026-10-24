# Wyniki testów akceptacyjnych

| Test | Status | Data |
|---|---|---|
| T1 Blokada i raportowanie podatności kodu (SAST/SCA) | ⏳ etap 11/13 | — |
| T2 Centralizacja raportów (SARIF) | ⏳ etap 11 | — |
| T3 Integralność i weryfikacja podpisów Cosign | ⏳ etap 14 | — |
| T4 Brama wdrożeniowa | ✅ zaliczony | 2026-10-24 |
| T5 Szczelność sekretów | ⏳ etap 12 | — |

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
