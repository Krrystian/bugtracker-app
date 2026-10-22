# Bugtracker

Prosty bugtracker (FastAPI + PostgreSQL) — aplikacja do projektu „Bezpieczny potok GitOps (DevSecOps)”.
Gałąź `main` to wersja secure. Podatne warianty żyją wyłącznie na gałęziach `vuln/*`.

## Uruchomienie w Dockerze (zalecane)

Wymaga Docker Desktop i pliku `.env` (skopiuj z `.env.example`, uzupełnij `DB_PASSWORD` i `SECRET_KEY`).

```bash
docker compose up -d --build   # build obrazu + start aplikacji i PostgreSQL
docker compose ps              # oba kontenery powinny być "healthy"
open http://localhost:8000     # interfejs webowy
docker compose logs -f app     # logi aplikacji
docker compose down            # stop (dane zostają w wolumenie db-data)
docker compose down -v         # stop + usunięcie danych
```

Obraz: multi-stage, przypięty `python:3.12.15-slim-trixie` (digest), użytkownik bez roota (UID 10001), system plików tylko do odczytu, `cap_drop: ALL`. Baza nie wystawia portu na zewnątrz.

## Kubernetes w Docker Desktop (manifesty statyczne, etap 3)

Wymaga włączonego Kubernetes w Docker Desktop (kontekst `docker-desktop`) i kontrolera Ingress Traefik.

```bash
# 1. Kontroler Ingress (jednorazowo)
helm repo add traefik https://traefik.github.io/charts
helm install traefik traefik/traefik --version 41.6.1 -n traefik --create-namespace --set service.type=LoadBalancer

# 2. Obraz: klaster Docker Desktop (kind) nie widzi lokalnych obrazów, trzeba go załadować do węzła
docker build -t bugtracker:local .
docker save bugtracker:local | docker exec -i desktop-control-plane ctr -n k8s.io images import --all-platforms -

# 3. Namespace + sekret (tworzony ręcznie z .env, NIE trafia do repo)
kubectl apply -f k8s/namespace.yaml
( set -a; . ./.env; set +a; kubectl -n bugtracker create secret generic bugtracker-secrets \
    --from-literal=db-password="$DB_PASSWORD" --from-literal=secret-key="$SECRET_KEY" )

# 4. Wdrożenie
kubectl apply -f k8s/
kubectl -n bugtracker get pods
open http://localhost
```

Manifesty: namespace z Pod Security `restricted`, PostgreSQL (UID 70) z PVC, aplikacja w 2 replikach (UID 10001), oba kontenery z read-only FS, `drop: ALL`, limitami i sondami zdrowia.

## Klaster k3d + wykres Helm (etapy 5–6)

k3d uruchamia lekki Kubernetes (k3s) w kontenerach Dockera; Traefik jest wbudowany. Aplikację wdraża wykres Helm `charts/bugtracker`, obraz pobierany jest z Docker Hub (tag = pełny SHA commita z `main`).

```bash
brew install k3d helm
k3d cluster create bugtracker --port "80:80@loadbalancer"   # port 80 musi być wolny

kubectl apply -f k8s/namespace.yaml                          # namespace z Pod Security "restricted"
( set -a; . ./.env; set +a; kubectl -n bugtracker create secret generic bugtracker-secrets \
    --from-literal=db-password="$DB_PASSWORD" --from-literal=secret-key="$SECRET_KEY" )

helm install bugtracker charts/bugtracker -n bugtracker --set image.tag=$(git rev-parse origin/main)
curl http://localhost/health

# aktualizacja do nowego obrazu
helm upgrade bugtracker charts/bugtracker -n bugtracker --reuse-values --set image.tag=<SHA>
```

Najważniejsze wartości (`charts/bugtracker/values.yaml`):

| Klucz | Domyślnie | Opis |
|---|---|---|
| `image.repository` | `krys3x15/bugtracker` | repozytorium obrazu |
| `image.tag` | *(wymagany)* | pełny SHA commita; pusty lub `latest` → błąd renderowania |
| `replicaCount` | `2` | liczba replik aplikacji |
| `existingSecret` | `bugtracker-secrets` | sekret z kluczami `db-password`, `secret-key` (tworzony poza chartem) |
| `ingress.host` / `ingress.className` | `localhost` / `traefik` | adres i kontroler Ingress |
| `database.enabled` | `true` | PostgreSQL w klastrze (PVC zachowywany po `helm uninstall`) |
| `networkPolicy.enabled` | `true` | default-deny; aplikacja tylko z Traefika, baza tylko z aplikacji, brak wyjścia do internetu |

Statyczne manifesty z etapu 3 zostają w `k8s/` (Docker Desktop, obraz lokalny).

## Cloudflare Tunnel dla webhooka (etap 7)

Wariant **Quick Tunnel**: bez konta i domeny, publiczny adres `https://<losowe-słowa>.trycloudflare.com`, który **zmienia się po każdym restarcie** poda `cloudflared`.

Tunel służy wyłącznie do webhooka GitHub → Argo CD. `cloudflared` wysyła każde żądanie do Traefika z nagłówkiem `Host: argo-webhook.tunnel`; jedyna trasa dla tego hosta to dokładna ścieżka `/api/webhook`. Wszystko inne (UI Argo CD, aplikacja, `/health`) daje 404.

```bash
kubectl apply -f infra/webhook-test/whoami.yaml     # TYMCZASOWO: atrapa Argo CD (do etapu 8)
kubectl apply -f infra/cloudflared/cloudflared.yaml
scripts/tunnel-url.sh                                # aktualny publiczny adres

curl -X POST "$(scripts/tunnel-url.sh)/api/webhook"  # 200
curl "$(scripts/tunnel-url.sh)/"                     # 404
```

| Plik | Opis |
|---|---|
| `infra/cloudflared/cloudflared.yaml` | namespace (PSA restricted), Deployment `cloudflared` 2026.10.0 (przypięty digest, non-root, read-only FS), NetworkPolicy: brak ruchu przychodzącego, wychodzący tylko DNS, Traefik i Cloudflare (443, 7844) |
| `infra/webhook-test/whoami.yaml` | tymczasowy backend + Ingress `argo-webhook.tunnel` / `/api/webhook` (Exact) |
| `scripts/tunnel-url.sh` | odczyt aktualnego adresu z logów `cloudflared` |

Przejście na własną domenę: `cloudflared tunnel run` z tokenem z Cloudflare Zero Trust (Secret / SealedSecret), stały adres webhooka; trasa `argo-webhook.tunnel` w klastrze zostaje bez zmian.

## Uruchomienie lokalne (bez Dockera)

```bash
brew install postgresql@16 && brew services start postgresql@16
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cp .env.example .env   # uzupełnij DB_PASSWORD i SECRET_KEY
.venv/bin/uvicorn app.main:app --port 8000
curl localhost:8000/health
```

Testy: `.venv/bin/pytest -q` (SQLite w pamięci, nie wymagają bazy).

## Interfejs webowy

Po uruchomieniu otwórz **http://localhost:8000** (przekierowuje na `/ui`): rejestracja, logowanie, lista zgłoszeń z filtrem statusu, dodawanie, edycja i usuwanie (tylko własnych zgłoszeń).

Strony renderuje serwer (Jinja2), bez JavaScriptu.

## API

| Metoda | Ścieżka | Auth | Opis |
|---|---|---|---|
| GET | `/health` | — | stan aplikacji i bazy |
| POST | `/auth/register` | — | rejestracja (`email`, `password` ≥ 12 znaków) |
| POST | `/auth/login` | — | zwraca token JWT |
| GET/POST | `/bugs` | Bearer | lista / utworzenie zgłoszenia |
| GET/PATCH/DELETE | `/bugs/{id}` | Bearer | odczyt / edycja / usunięcie (edycja i usuwanie tylko przez zgłaszającego) |

## Konfiguracja (zmienne środowiskowe)

`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `SECRET_KEY` (≥ 32 znaki), opcjonalnie `ENABLE_DOCS=true` (Swagger pod `/docs`) i `COOKIE_SECURE=true` (gdy aplikacja działa po HTTPS).

## Zabezpieczenia w wersji secure

- zapytania wyłącznie przez ORM SQLAlchemy (parametryzowane),
- hasła hashowane Argon2id, porównanie odporne na timing przy nieistniejącym użytkowniku,
- JWT z wymaganym `exp`, autoryzacja właściciela przy edycji/usuwaniu,
- walidacja wejścia (Pydantic), nagłówki bezpieczeństwa (ścisłe CSP bez inline/JS, `nosniff`, `X-Frame-Options`),
- frontend: automatyczne escapowanie HTML w Jinja2 (ochrona przed XSS), sesja w ciasteczku `HttpOnly` + `SameSite=Strict`, token CSRF w każdym formularzu,
- brak sekretów w kodzie — wszystko ze zmiennych środowiskowych.
