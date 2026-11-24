# Example TUI Configurations

Common configuration patterns for different use cases.

## Minimal Cluster (Development)

**Use case:** Testing Kubernetes features locally, minimal resource usage

### Configuration Tab
```
Network CIDR: 192.168.56.0/24
controlplane: 192.168.56.10
node01: 192.168.56.11
node02: 192.168.56.12

✅ deploy_storage (storage_backend: local-path)
❌ services_vm_enabled
❌ deploy_secrets
❌ deploy_kyverno
❌ deploy_traefik
❌ deploy_jenkins
❌ deploy_monitoring
❌ deploy_mysql
```

**Resources:** ~9GB RAM (3 VMs)

**Features:** Bare Kubernetes with local-path storage

---

## Full Stack with GitLab CI/CD

**Use case:** Complete CI/CD pipeline with Git hosting and container registry

### Configuration Tab
```
Network CIDR: 192.168.56.0/24
controlplane: 192.168.56.10
node01: 192.168.56.11
node02: 192.168.56.12
secrets: 192.168.56.20
services: 192.168.56.80

✅ services_vm_enabled
✅ deploy_secrets
✅ deploy_storage (storage_backend: nfs)
✅ deploy_kyverno
✅ deploy_traefik
✅ deploy_jenkins
✅ deploy_monitoring
❌ deploy_mysql
```

### Services Tab
```
GitLab:
  HTTP Port: 80
  SSH Port: 2222
  Registry Port: 5050
  Data Directory: /srv/gitlab
  Puma Workers: 2

Nexus:
  HTTP Port: 8081
  Data Path: /srv/nexus

Harbor:
  HTTP Port: 8880

NFS:
  Export Path: /srv/nfs/k8s
```

**Resources:** about 13GB RAM (5 VMs at the inventory defaults)

**Access:**
- GitLab: http://192.168.56.80
- Nexus: http://192.168.56.80:8081
- Harbor: http://192.168.56.80:8880
- Traefik Dashboard: http://traefik.fss (add to /etc/hosts)
- Grafana: http://grafana.fss

---

## Lightweight Git + Monitoring

**Use case:** Simple Git hosting with cluster monitoring, no heavy services

### Configuration Tab
```
Network CIDR: 192.168.56.0/24
controlplane: 192.168.56.10
node01: 192.168.56.11
node02: 192.168.56.12
secrets: 192.168.56.20
services: 192.168.56.80

✅ services_vm_enabled
✅ deploy_secrets
✅ deploy_storage (storage_backend: longhorn)
❌ deploy_kyverno
✅ deploy_traefik
❌ deploy_jenkins
✅ deploy_monitoring
❌ deploy_mysql
```

### Services Tab
```
Gitea:  # Use Gitea instead of heavy GitLab
  HTTP Port: 3000
  SSH Port: 2224
  Data Path: /srv/gitea

NFS:
  Export Path: /srv/nfs/k8s

# GitLab/Nexus/Harbor can be left at defaults (won't be deployed)
```

**Resources:** about 13GB RAM (5 VMs at the inventory defaults; increase worker RAM if using Longhorn)

**Why this setup:**
- Gitea is much lighter than GitLab (~50MB vs 2GB RAM)
- Longhorn provides replicated storage (data survives node loss)
- Prometheus + Grafana for monitoring
- Traefik for ingress

---

## Services VM with Harbor Configuration

**Use case:** Configure Harbor on the Services VM. Enabling `services_vm_enabled` also deploys GitLab, Gitea, and Nexus in this repository.

### Configuration Tab
```
Network CIDR: 192.168.56.0/24
controlplane: 192.168.56.10
node01: 192.168.56.11
node02: 192.168.56.12
secrets: 192.168.56.20
services: 192.168.56.80

✅ services_vm_enabled
✅ deploy_secrets  # Harbor password comes from OpenBao
✅ deploy_storage (storage_backend: local-path)
❌ deploy_kyverno
❌ deploy_traefik
❌ deploy_jenkins
❌ deploy_monitoring
❌ deploy_mysql
```

### Services Tab
```
Harbor:
  HTTP Port: 8880
  Install Directory: /opt/harbor
  Data Volume: /data

# Other services left at defaults (won't deploy)
```

**Resources:** about 13GB RAM (5 VMs at the inventory defaults)

**Features:**
- Secure container registry
- Vulnerability scanning (Trivy)
- Image signing
- Admin password stored in OpenBao

---

## Port Customization Example

**Scenario:** Avoid common port conflicts by shifting everything

### Services Tab
```
GitLab:
  HTTP Port: 8080  # Instead of 80
  SSH Port: 2222
  Registry Port: 5050

Nexus:
  HTTP Port: 9081  # Instead of 8081

Gitea:
  HTTP Port: 3030  # Instead of 3000
  SSH Port: 2224

Harbor:
  HTTP Port: 9880  # Instead of 8880
```

**Access URLs:**
- GitLab: http://192.168.56.80:8080
- Nexus: http://192.168.56.80:9081
- Gitea: http://192.168.56.80:3030
- Harbor: http://192.168.56.80:9880

---

## Tips

1. **Start minimal** - Enable features one at a time, run Ansible after each
2. **RAM planning:**
   - Bare cluster: 9GB
   - +Secrets VM: +1GB
   - +Services VM (GitLab): +3GB
   - +Monitoring: +1GB
   
3. **Storage backends:**
   - `local-path`: Lightest, data stays on node
   - `longhorn`: Replicated, survives node loss
   - `nfs`: Shared, requires services VM

4. **Dependencies:**
   - Traefik needs `deploy_secrets`
   - Jenkins/Monitoring/MySQL need `deploy_storage` + `deploy_secrets`
   - NFS storage needs `services_vm_enabled`

5. **Port conflicts:**
   - GitLab takes port 80, so Harbor uses 8880
   - Customize in Services tab if needed
   - Nexus registry is fixed at 5002 (in main.yml)
