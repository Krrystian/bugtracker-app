# Start dla zespołu

Jak uruchomić projekt na własnym komputerze i jak wprowadzać zmiany. Polecenia zakładają macOS lub Linux; na Windowsie uruchamiaj je w **WSL2** (Ubuntu) z Docker Desktop zintegrowanym z WSL.

| Poziom | Co dostajesz | Czas | Wymagane narzędzia |
|---|---|---|---|
| 1. Docker Compose | aplikacja + baza na `http://localhost:8000` | ~5 min | Docker Desktop |
| 2. Testy | 15 testów jednostkowych | ~2 min | Python 3.12 |
| 3. Pełny klaster | k3d + Sealed Secrets + Argo CD (+ Kyverno), jak na klastrze referencyjnym | ~10 min | Docker Desktop, `k3d`, `kubectl`, `helm` |

## 0. Repozytoria

```bash
git clone https://github.com/Krrystian/bugtracker-app.git
git clone https://github.com/Krrystian/bugtracker-gitops.git   # potrzebne tylko do zmian w GitOps
cd bugtracker-app
```

## 1. Aplikacja w Docker Compose

```bash
cp .env.example .env
# w .env uzupełnij dwie wartości (dowolne, tylko lokalne):
#   DB_PASSWORD=$(openssl rand -hex 24)
#   SECRET_KEY=$(openssl rand -hex 32)
docker compose up -d --build
docker compose ps                  # oba kontenery "healthy"
open http://localhost:8000         # Linux/WSL: xdg-open albo wklej adres do przeglądarki
docker compose down                # stop (dodaj -v, żeby skasować dane)
```

`.env` jest w `.gitignore` — nigdy go nie commituj.

## 2. Testy

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q                # SQLite w pamięci, baza nie jest potrzebna
```

## 3. Pełny klaster (jak na prezentacji)

Instalacja narzędzi (macOS): `brew install k3d kubectl helm`. Linux: [k3d](https://k3d.io/#installation), [kubectl](https://kubernetes.io/docs/tasks/tools/), [helm](https://helm.sh/docs/intro/install/).

```bash
scripts/bootstrap-cluster.sh
```

Skrypt sam tworzy klaster `bugtracker`, instaluje Sealed Secrets i Argo CD (wersje przypięte, pliki sprawdzane sumą SHA-256), tworzy sekret aplikacji i wdraża `Application` z repo GitOps. Na końcu wypisuje adres aplikacji (`http://localhost`) i jak wejść do panelu Argo CD.

Opcje (zmienne środowiskowe):

| Zmienna | Domyślnie | Kiedy zmienić |
|---|---|---|
| `HTTP_PORT` | `80` | port 80 zajęty (np. inny klaster, serwer WWW) → `HTTP_PORT=8081` |
| `CLUSTER` | `bugtracker` | chcesz drugi klaster obok |
| `WITH_KYVERNO` | `0` | `1` = także weryfikacja podpisów Cosign; skrypt poprosi o login i token **tylko do odczytu** z własnego darmowego konta Docker Hub (Account settings → Personal access tokens → Read-only) |
| `SEALED_KEY` | — | ścieżka do kopii klucza kontrolera Sealed Secrets (patrz niżej) |

Uwaga: `k3d cluster create` przełącza domyślny kontekst `kubectl` na nowy klaster. Sprawdzisz go `kubectl config current-context`.

### Czym Twój klaster różni się od referencyjnego

- **Argo CD pokaże `Degraded`** — to oczekiwane. Pliki `SealedSecret` w repo GitOps są zaszyfrowane kluczem klastra referencyjnego i Twój kontroler ich nie odszyfruje (`no key could decrypt secret`). Skrypt tworzy więc lokalny `bugtracker-secrets` z losowymi wartościami i aplikacja działa normalnie. Pełną zgodność daje tylko kopia klucza kontrolera (`SEALED_KEY=…`), którą przekazuje właściciel repo **poza GitHubem** (np. menedżer haseł) — to klucz prywatny, nie wysyłaj go czatem ani mailem.
- **Brak webhooka i tunelu.** Webhook GitHuba wskazuje na jeden adres — klaster referencyjny. Twoje Argo CD samo sprawdza repo GitOps co ok. 3 minuty (albo kliknij **Refresh** w UI).
- **Argo CD wdraża `main` repo GitOps**, więc pokazuje dokładnie to, co produkcja.

Usunięcie klastra: `k3d cluster delete bugtracker`.

## 4. Jak wprowadzać zmiany

```bash
git switch main && git pull
git switch -c feat/krotki-opis
# ... zmiany, testy ...
git commit -m "feat: krótki opis po polsku"
git push -u origin feat/krotki-opis
gh pr create --fill                # albo przez stronę GitHuba
```

- `main` jest chroniony: tylko przez PR, wymagane zielone wszystkie joby CI (testy, Semgrep, OSV-Scanner, Checkov, Gitleaks, Hadolint, build, Trivy, ZAP).
- Czerwony skaner = znalezisko w Twojej zmianie. Szczegóły: zakładka **Security → Code scanning** albo log joba. Nie wyłączaj skanera ani nie dodawaj `continue-on-error`.
- **Gałęzie `vuln/*` są celowo podatne** (demonstracja bramek). Nigdy ich nie merge'uj ani nie kopiuj z nich kodu do `main`.
- Po merge'u do `main` CI publikuje podpisany obraz i robi commit z nowym tagiem na gałęzi `development` repo GitOps. **Wdrożenie** = PR `development → main` w `bugtracker-gitops` (wymaga uprawnień do tamtego repo).
- Nigdy nie commituj haseł, tokenów ani `.env`. Gitleaks i tak zatrzyma PR.

## Problemy

| Objaw | Przyczyna / rozwiązanie |
|---|---|
| `port is already allocated` przy tworzeniu klastra | port 80 zajęty → `HTTP_PORT=8081 scripts/bootstrap-cluster.sh` |
| `Docker is not running` | uruchom Docker Desktop i poczekaj, aż ikonka przestanie się animować |
| pody `ImagePullBackOff` z `toomanyrequests` | limit anonimowych pobrań Docker Hub → `docker login` i po kilku minutach `kubectl -n bugtracker delete pod --all` |
| z Kyverno: pod obrazu z `main` odrzucony (`admission webhook ... denied the request`) | brak lub zły token w sekrecie `dockerhub-readonly` (namespace `kyverno`) |
| aplikacja nie odpowiada na `localhost` | `kubectl -n bugtracker get pods`, potem `kubectl -n bugtracker logs deploy/bugtracker` |
| Argo CD `Degraded` | patrz wyżej — bez klucza kontrolera to normalne, o ile pody są `Running` |
