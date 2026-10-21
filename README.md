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

## Klaster k3d (etap 5)

k3d uruchamia lekki Kubernetes (k3s) w kontenerach Dockera; Traefik jest wbudowany. Obraz pobierany jest z Docker Hub (tag = SHA commita z `main`).

```bash
brew install k3d
k3d cluster create bugtracker --port "80:80@loadbalancer"   # port 80 musi być wolny

kubectl apply -f k8s/namespace.yaml
( set -a; . ./.env; set +a; kubectl -n bugtracker create secret generic bugtracker-secrets \
    --from-literal=db-password="$DB_PASSWORD" --from-literal=secret-key="$SECRET_KEY" )
kubectl apply -f k8s/pvc.yaml -f k8s/service.yaml -f k8s/ingress.yaml

# deployment.yaml wskazuje lokalny obraz (etap 3) — podmieniamy na obraz z Docker Hub
SHA=$(git rev-parse origin/main)
sed -e "s#image: bugtracker:local#image: krys3x15/bugtracker:$SHA#" \
    -e "s#imagePullPolicy: Never#imagePullPolicy: IfNotPresent#" k8s/deployment.yaml | kubectl apply -f -

curl http://localhost/health
```

Od etapu 6 tę podmianę zastępuje wykres Helm (`image.tag` w values).

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
