# Services VM Reference

This document explains each service on the Services VM and how to access them.

## Prerequisites

The Services VM must be enabled in the Configuration tab (`services_vm_enabled: true`).

Default Services VM IP: `192.168.56.80`

## Services Overview

### GitLab (Git Repository + CI/CD)

**Purpose:** Git repository management, CI/CD pipelines, container registry

**Default Ports:**
- HTTP: `80` → Access at `http://192.168.56.80`
- SSH: `2222` → Clone via `git@192.168.56.80:2222`
- Registry: `5050` → Docker registry at `192.168.56.80:5050`

**Configuration Options:**
- `gitlab_http_port` - Web interface port
- `gitlab_ssh_port` - Git SSH port
- `gitlab_registry_port` - Container registry port
- `gitlab_data_dir` - Persistent data location (default: `/srv/gitlab`)
- `gitlab_puma_workers` - Application server workers (default: 2)

**First Login:**
- Username: `root`
- Password: Set during first access (check container logs or reset)

**Resources:**
- RAM: Uses significant memory (~2GB minimum)
- Disk: Stores repositories, CI artifacts, container images

---

### Nexus (Artifact Repository + Docker Registry)

**Purpose:** Maven/npm/PyPI artifacts, Docker registry

**Default Ports:**
- HTTP: `8081` → Access at `http://192.168.56.80:8081`
- Docker Registry: `5002` → `192.168.56.80:5002`

**Configuration Options:**
- `nexus_http_port` - Web UI port
- `nexus_data_path` - Data storage (default: `/srv/nexus`)
- Registry port `5002` is fixed (configured in `main.yml`)

**First Login:**
- Username: `admin`
- Password: Located in `/srv/nexus/admin.password` on first start

**Use Cases:**
- Maven repository proxy
- npm/PyPI package cache
- Docker image registry (alternative to Harbor)
- CI/CD artifact storage

---

### Gitea (Lightweight Git Service)

**Purpose:** Simple, lightweight Git hosting (GitLab alternative)

**Default Ports:**
- HTTP: `3000` → Access at `http://192.168.56.80:3000`
- SSH: `2224` → Clone via `git@192.168.56.80:2224`

**Configuration Options:**
- `gitea_http_port` - Web interface port
- `gitea_ssh_port` - Git SSH port
- `gitea_data_path` - Data location (default: `/srv/gitea`)

**First Login:**
- Create admin account on first visit
- SQLite database (no external DB needed)

**Why Gitea over GitLab?**
- Much lighter weight (~50MB RAM vs 2GB)
- Faster startup
- No CI/CD (just Git hosting)

---

### Harbor (Container Registry + Security Scanning)

**Purpose:** Enterprise-grade container registry with vulnerability scanning

**Default Ports:**
- HTTP: `8880` → Access at `http://192.168.56.80:8880`
  - Port 80 is taken by GitLab, so Harbor uses 8880

**Configuration Options:**
- `harbor_http_port` - Web UI and registry port
- `harbor_install_dir` - Installation path (default: `/opt/harbor`)
- `harbor_data_volume` - Data storage (default: `/data`)

**First Login:**
- Username: `admin`
- Password: Stored in OpenBao at `kv/bootstrap/harbor` (field: `admin-password`)
  - Ansible reads this during deployment

**Features:**
- Container vulnerability scanning (Trivy)
- Replication to other registries
- RBAC and project management
- Image signing (Notary)

**Push/Pull Images:**
```bash
# Login
docker login 192.168.56.80:8880 -u admin

# Tag and push
docker tag myimage:latest 192.168.56.80:8880/library/myimage:latest
docker push 192.168.56.80:8880/library/myimage:latest
```

---

### NFS Server (Shared Storage)

**Purpose:** Network file system for Kubernetes PersistentVolumes

**Default Configuration:**
- Export Path: `/srv/nfs/k8s`
- Clients: Only cluster node IPs (10.0.0.11, 10.0.0.12, etc.)
- Options: `rw,sync,no_subtree_check,no_root_squash`

**Configuration Options:**
- `nfs_path` - Root export directory (default: `/srv/nfs/k8s`)

**Security:**
- NOT exported to the entire subnet (restricted to cluster nodes)
- `no_root_squash` enabled for MySQL/Grafana/Jenkins (they chown data dirs)
- Kyverno policy blocks direct `nfs:` pod volumes (only NFS provisioner can use it)

**Storage Backend:**
- Set `storage_backend: nfs` in Configuration tab
- This creates an NFS-based StorageClass in Kubernetes
- PVCs automatically create subdirectories under `/srv/nfs/k8s`

---

## Port Summary

| Service | Type | Port | URL |
|---------|------|------|-----|
| GitLab | HTTP | 80 | http://192.168.56.80 |
| GitLab | SSH | 2222 | git@192.168.56.80:2222 |
| GitLab Registry | Docker | 5050 | 192.168.56.80:5050 |
| Nexus | HTTP | 8081 | http://192.168.56.80:8081 |
| Nexus Registry | Docker | 5002 | 192.168.56.80:5002 |
| Gitea | HTTP | 3000 | http://192.168.56.80:3000 |
| Gitea | SSH | 2224 | git@192.168.56.80:2224 |
| Harbor | HTTP | 8880 | http://192.168.56.80:8880 |
| NFS | - | 2049 | mount -t nfs 192.168.56.80:/srv/nfs/k8s |

## Common Workflows

### Using GitLab for CI/CD

1. Enable Services VM and Secrets in Configuration
2. Deploy with Ansible
3. Access GitLab at http://192.168.56.80
4. Create a project, add `.gitlab-ci.yml`
5. Runners can push images to GitLab Registry (port 5050)

### Using Nexus as Docker Registry

1. Configure cluster nodes to trust insecure registry (Ansible does this)
2. Access Nexus at http://192.168.56.80:8081
3. Create a Docker (hosted) repository on port 5002
4. Push/pull: `docker tag myimage 192.168.56.80:5002/myimage`

### Using Harbor with Kubernetes

1. Add ImagePullSecrets to pods:
   ```bash
   kubectl create secret docker-registry harbor \
     --docker-server=192.168.56.80:8880 \
     --docker-username=admin \
     --docker-password=<from-openbao>
   ```

2. Reference in pod spec:
   ```yaml
   spec:
     imagePullSecrets:
     - name: harbor
     containers:
     - image: 192.168.56.80:8880/library/myapp:latest
   ```

### Using NFS for Persistent Storage

1. Set `storage_backend: nfs` in Configuration
2. Deploy storage role with Ansible
3. Create a PVC:
   ```yaml
   apiVersion: v1
   kind: PersistentVolumeClaim
   metadata:
     name: my-data
   spec:
     accessModes: [ReadWriteMany]
     storageClassName: nfs
     resources:
       requests:
         storage: 10Gi
   ```

4. NFS provisioner auto-creates `/srv/nfs/k8s/my-namespace-my-data-pvc-xxxx`

---

## Troubleshooting

**GitLab is slow/unresponsive**
- Increase `gitlab_puma_workers` (default: 2)
- Check RAM on Services VM (needs 3GB+ for GitLab alone)

**Nexus shows "503 Service Unavailable"**
- Still starting up (can take 1-2 minutes)
- Check: `docker logs nexus` on services VM

**Harbor admin password unknown**
- Read from OpenBao:
  ```bash
  export BAO_ADDR=https://192.168.56.20:8200
  export BAO_CACERT=ansible/fetched/pki/ca.crt
  export BAO_TOKEN=$(jq -r .root_token ansible/fetched/openbao/init.json)
  bao kv get kv/bootstrap/harbor
  ```

**NFS mount fails from pods**
- Check exports: `showmount -e 192.168.56.80`
- Verify cluster node IPs are in `/etc/exports` on services VM
- Test mount from a node: `mount -t nfs 192.168.56.80:/srv/nfs/k8s /mnt`

**Port conflicts**
- All ports are configurable in the Services tab
- Restart services after changing ports (run Ansible playbook again)
