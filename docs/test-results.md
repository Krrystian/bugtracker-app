# Testy akceptacyjne

Wszystkie pięć testów zostało zaliczonych 24 października 2026.

## T1: zablokowanie podatnej biblioteki

Wysłaliśmy gałąź `vuln/sca-deps` ze starą biblioteką `urllib3 1.22`, która ma krytyczną podatność CVE-2018-20060.

Wynik ([przebieg](https://github.com/Krrystian/bugtracker-app/actions/runs/40075903495)): OSV-Scanner zatrzymał pipeline, a reszta jobów przeszła. Obraz nie trafił do Docker Hub. W zakładce Security pojawił się alert wskazujący `urllib3@1.22`.

## T2: wszystkie raporty w jednym miejscu

Wysłaliśmy gałąź `vuln/helm-privileged`, w której kontener działa jako root.

Wynik ([przebieg](https://github.com/Krrystian/bugtracker-app/actions/runs/40078615628)): Checkov zatrzymał pipeline i wysłał raport. W zakładce Security są alerty, np. „Minimize the admission of root containers” wskazujący `deployment.yaml`.

W tej samej zakładce są raporty wszystkich skanerów: Semgrep, OSV-Scanner, Checkov i OWASP ZAP. Można to sprawdzić komendą:

```bash
gh api 'repos/Krrystian/bugtracker-app/code-scanning/analyses?ref=refs/heads/main' --jq '[.[].tool.name] | unique'
```

## T3: blokada niepodpisanego obrazu

W repo GitOps na gałęzi `vuln/unsigned-image` podmieniliśmy obraz na `nginx:1.27.3-alpine`, który nie jest podpisany naszym kluczem. Gałąź wdrożyliśmy w piaskownicy (namespace `sandbox`).

Wynik: Kyverno nie pozwolił utworzyć poda:

```
Policy verify-bugtracker-images failed: image is not signed with the project Cosign key (cosign.pub)
```

Dla porównania nasz podpisany obraz z `main` uruchamia się normalnie.

Po drodze trzeba było rozwiązać trzy problemy:
- Stary typ polityki Kyverno (`ClusterPolicy`) nie widział podpisów w nowym formacie Cosign 3, więc użyliśmy `ImageValidatingPolicy`.
- Kyverno zmieniał Deployment, przez co Argo CD stale pokazywał różnicę z Git. Teraz Kyverno sprawdza tylko pody.
- Kyverno trafiał na limit zapytań Docker Hub dla anonimowych użytkowników. Dostał token tylko do odczytu (sekret `dockerhub-readonly`, poza Git).

## T4: ręczne zatwierdzanie wdrożenia

Scaliliśmy zmianę do `main` w repo aplikacji.

Wynik:
- CI zbudowało obraz, wysłało go do Docker Hub i powiadomiło repo GitOps ([przebieg](https://github.com/Krrystian/bugtracker-app/actions/runs/40072560307)).
- Repo GitOps dostało commit z nowym tagiem tylko na gałęzi `development` ([przebieg](https://github.com/Krrystian/bugtracker-gitops/actions/runs/40072686137)).
- Na `main` repo GitOps i w klastrze nic się nie zmieniło.

Nowa wersja trafia do klastra dopiero po ręcznym PR `development` → `main`.

Sprawdzenie:

```bash
git -C bugtracker-gitops show origin/development:environments/development/values.yaml | grep tag:
git -C bugtracker-gitops show origin/main:environments/development/values.yaml | grep tag:
kubectl -n bugtracker get deploy bugtracker -o jsonpath='{.spec.template.spec.containers[0].image}'
```

## T5: szczelność sekretów

Wygenerowaliśmy losowy sekret i od razu zaszyfrowaliśmy go `kubeseal`. Do repo GitOps trafił tylko zaszyfrowany plik `bugtracker-t5-demo.sealedsecret.yaml` ([PR #6](https://github.com/Krrystian/bugtracker-gitops/pull/6)). Argo CD go wdrożył, a kontroler Sealed Secrets odszyfrował go w klastrze.

Wynik:
- wartość w klastrze zgadza się z oryginałem (porównaliśmy skróty SHA-256, nie samą wartość),
- jawnej wartości nie ma w historii git żadnego z repo, w logach Argo CD, kontrolera Sealed Secrets ani CI.

Dodatkowo gałąź `vuln/plaintext-secret` z jawnym hasłem została zatrzymana przez Gitleaks ([przebieg](https://github.com/Krrystian/bugtracker-gitops/actions/runs/40099839420)).

## Bramki skanerów

Na każdej gałęzi `vuln/*` pipeline kończy się błędem na zaplanowanym skanerze, obraz nie trafia do Docker Hub i nic nie idzie do repo GitOps. `main` przechodzi.

Sprawdziliśmy to, porównując commity z gałęzi `vuln/*` z listą tagów w Docker Hub i z commitami na gałęzi `development` repo GitOps. Żaden commit z `vuln/*` tam nie trafił.
