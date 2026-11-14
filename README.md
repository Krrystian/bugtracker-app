# Bugtracker

Prosta aplikacja do zgłaszania błędów (FastAPI + PostgreSQL) wdrażana bezpiecznym, zautomatyzowanym potokiem **DevSecOps** i **GitOps**.

- `main` to bezpieczna wersja aplikacji.
- Gałęzie `vuln/*` celowo zawierają po jednej podatności, żeby pokazać, że potok ją zatrzyma.

## Jak to działa

```
push na main ─► CI: testy + skanery bezpieczeństwa ─► obraz w Docker Hub (podpisany Cosign)
                                                     │
                                                     ▼
              repo GitOps: nowy tag na gałęzi development ─► ręczny PR do main
                                                     │
                                                     ▼
              webhook ─► Argo CD wdraża w klastrze k3d ─► Kyverno wpuszcza tylko podpisane obrazy
```

1. **CI (GitHub Actions)** testuje kod i uruchamia skanery. Jeśli którykolwiek znajdzie poważny problem, obraz nie jest publikowany.
2. Obraz z `main` trafia do Docker Hub i jest **podpisywany** (Cosign).
3. Nowa wersja trafia do repozytorium [bugtracker-gitops](https://github.com/Krrystian/bugtracker-gitops). Wdrożenie wymaga ręcznego zatwierdzenia (PR).
4. **Argo CD** wdraża aplikację do Kubernetes, a **Kyverno** odrzuca obrazy bez podpisu.
5. Hasła są przechowywane w repo tylko w postaci zaszyfrowanej (**Sealed Secrets**).

## Skanery bezpieczeństwa

| Skaner | Co sprawdza |
|---|---|
| Semgrep | błędy bezpieczeństwa w kodzie (np. SQL injection) |
| OSV-Scanner | podatne biblioteki |
| Checkov | konfigurację Kubernetes i Helm |
| Hadolint | dobre praktyki w Dockerfile |
| Gitleaks | hasła i klucze w kodzie |
| Trivy | podatności w obrazie Dockera |
| OWASP ZAP | działającą aplikację (testy z zewnątrz) |

Wyniki trafiają do zakładki **Security** repozytorium. Szczegóły: [docs/scan-results.md](docs/scan-results.md).

## Uruchomienie

Wymaga Docker Desktop. Skopiuj `.env.example` do `.env` i uzupełnij `DB_PASSWORD` oraz `SECRET_KEY`.

```bash
docker compose up -d --build
open http://localhost:8000
```

Testy: `pytest -q`. Uruchomienie w Kubernetes (k3d, Helm, Argo CD): [docs/wdrozenie.md](docs/wdrozenie.md).

## Funkcje

- rejestracja i logowanie,
- lista zgłoszeń z filtrem statusu, dodawanie, edycja i usuwanie własnych zgłoszeń,
- API: `/health`, `/auth/register`, `/auth/login`, `/bugs`, `/bugs/{id}`.

## Zabezpieczenia aplikacji

- zapytania do bazy przez ORM (ochrona przed SQL injection),
- hasła hashowane algorytmem Argon2,
- automatyczne escapowanie HTML (ochrona przed XSS) i tokeny CSRF,
- nagłówki bezpieczeństwa, sesja w bezpiecznym ciasteczku,
- kontener bez uprawnień roota, brak haseł w kodzie.

## Dokumentacja

| Plik | Zawartość |
|---|---|
| [docs/wdrozenie.md](docs/wdrozenie.md) | instrukcje wdrożenia i konfiguracji |
| [docs/raport-kubernetes.md](docs/raport-kubernetes.md) | raport z wdrożenia w Kubernetes |
| [docs/vulnerabilities.md](docs/vulnerabilities.md) | lista podatności na gałęziach `vuln/*` |
| [docs/scan-results.md](docs/scan-results.md) | wyniki skanerów |
| [docs/test-results.md](docs/test-results.md) | testy akceptacyjne |
