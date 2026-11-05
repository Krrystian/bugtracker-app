# VULN-11: Montowanie wolumenu hostPath (Container Escape / Naruszenie izolacji węzła)

- **Branch:** `vuln/helm-hostpath`
- **Bramka:** job `IaC (Checkov)`.
- **Kategoria:** A05:2021 Security Misconfiguration, CWE-250 (Execution with Unnecessary Privileges), CWE-552 (Files or Directories Accessible to External Parties), MITRE ATT&CK T1611 (Escape to Host).

---

## 1. Na czym polega ta podatność?

W pliku `charts/bugtracker/templates/deployment.yaml` dodano montowanie gniazda Dockera węzła klastra do wnętrza kontenera aplikacji:

```yaml
volumeMounts:
  - name: docker-socket
    mountPath: /var/run/docker.sock
volumes:
  - name: docker-socket
    hostPath:
      path: /var/run/docker.sock
```

### Dlaczego jest to skrajnie niebezpieczne?
1. **Container Escape (Ucieczka z kontenera):**
   Gniazdo `/var/run/docker.sock` to interfejs API demona Dockera działającego na węźle klastra. Każdy proces w kontenerze, który ma dostęp do tego pliku, może wydawać dowolne polecenia demonowi Dockera na maszynie-matce.
2. **Przejęcie całego węzła (Root on Host):**
   Nawet jeśli aplikacja działa z konta bez uprawnień roota (UID 10001), mając dostęp do gniazda Dockera może uruchomić nowy kontener z flagami `--privileged -v /:/host` i uzyskać natychmiastowe, pełne prawa roota na fizycznym serwerze lub węźle klastra.
3. **Naruszenie profilu Pod Security Standards:**
   Oficjalny profil bezpieczeństwa Kubernetes **`restricted`** (oraz kontrolery przyjęć typu Kyverno) bezwzględnie zakazują używania typu wolumenów `hostPath`.

---

## 2. Jak przetestować tę podatność w praktyce (Checkov)

### Krok 1: Wyrenderuj manifest z wykresu Helm
```bash
docker run --rm -v "$PWD:/apps" -w /apps alpine/helm:3.16.4 template my-bugtracker charts/bugtracker --set image.tag=test123 > rendered-hostpath.yaml
```

### Krok 2: Uruchom skaner Checkov
```bash
docker run --rm -v "$PWD:/w" -w /w bridgecrew/checkov:3.3.26 -f /w/rendered-hostpath.yaml --framework kubernetes --compact
```

### Oczekiwany wynik skanowania:
Checkov natychmiast wykrywa naruszenie polityki bezpieczeństwa i zgłasza błąd blokujący:
- **`CKV_K8S_8: "Do not use hostPath volumes"`** (FAILED dla `Deployment.default.my-bugtracker`)
- **`CKV_K8S_27: "Do not expose hostPath volume /var/run/docker.sock"`** (FAILED dla `Deployment.default.my-bugtracker`)

---

## 3. Poprawka w gałęzi `main`

W gałęzi `main`:
- Żaden pod nie ma prawa montować wolumenów typu `hostPath`.
- Na dane tymczasowe używany jest bezpieczny wolumen w pamięci: `emptyDir: {}`.
- Na sekrety używany jest typ `secret`, a na bazę danych `PersistentVolumeClaim`.
- Namespace klastra ma wymuszoną etykietę `pod-security.kubernetes.io/enforce: restricted`, która odrzuca pody z wolumenami `hostPath` na poziomie API serwera.
