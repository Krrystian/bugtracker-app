# Bugtracker

Prosty bugtracker (FastAPI + PostgreSQL) — aplikacja do projektu „Bezpieczny potok GitOps (DevSecOps)”.
Gałąź `main` to wersja secure. Podatne warianty żyją wyłącznie na gałęziach `vuln/*`.

## Uruchomienie lokalne

```bash
brew install postgresql@16 && brew services start postgresql@16
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cp .env.example .env   # uzupełnij DB_PASSWORD i SECRET_KEY
.venv/bin/uvicorn app.main:app --port 8000
curl localhost:8000/health
```

Testy: `.venv/bin/pytest -q` (SQLite w pamięci, nie wymagają bazy).

## API

| Metoda | Ścieżka | Auth | Opis |
|---|---|---|---|
| GET | `/health` | — | stan aplikacji i bazy |
| POST | `/auth/register` | — | rejestracja (`email`, `password` ≥ 12 znaków) |
| POST | `/auth/login` | — | zwraca token JWT |
| GET/POST | `/bugs` | Bearer | lista / utworzenie zgłoszenia |
| GET/PATCH/DELETE | `/bugs/{id}` | Bearer | odczyt / edycja / usunięcie (edycja i usuwanie tylko przez zgłaszającego) |

## Konfiguracja (zmienne środowiskowe)

`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `SECRET_KEY` (≥ 32 znaki), opcjonalnie `ENABLE_DOCS=true` (Swagger pod `/docs`).

## Zabezpieczenia w wersji secure

- zapytania wyłącznie przez ORM SQLAlchemy (parametryzowane),
- hasła hashowane Argon2id, porównanie odporne na timing przy nieistniejącym użytkowniku,
- JWT z wymaganym `exp`, autoryzacja właściciela przy edycji/usuwaniu,
- walidacja wejścia (Pydantic), odpowiedzi tylko JSON, nagłówki bezpieczeństwa (CSP, `nosniff`, `X-Frame-Options`),
- brak sekretów w kodzie — wszystko ze zmiennych środowiskowych.
