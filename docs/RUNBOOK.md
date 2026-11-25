# Kubernetes-FAC Runbook

Step-by-step instructions to run each role, check that it works, and open it.
For architecture diagrams, see the editable SVG sources in `docs/architecture/`. The PDF guide is a generated snapshot and may not reflect the latest inventory values.

> These steps follow the current code. The full playbook has not yet been run end to end on
> fresh VMs, so if a step fails, the error message and the Troubleshooting section are the place to start.

---

## 0. Before you start

**On your laptop you need:**

- VirtualBox and Vagrant
- Ansible, with these collections:
  ```shell
  ansible-galaxy collection install kubernetes.core community.general community.crypto community.docker
  ```
- `kubectl` and `jq`
- Python `passlib`, used to hash the Traefik password: `pip install passlib`

**Allow VirtualBox's private network range (Linux/macOS, once):**
```shell
echo "* 0.0.0.0/0 ::/0" | sudo tee -a /etc/vbox/networks.conf
```

**Roles are selected explicitly by tag.** The optional VM settings in `ansible/inventories/lab/hosts.yml` describe which hosts exist; they do not enable application roles. Run prerequisites separately before dependent roles.

**Two helpers used throughout.** Run these from the repo root after secrets are enabled (section 4):
```shell
# kubectl from your laptop
export KUBECONFIG=$PWD/ansible/fetched/admin.conf

# read a secret from OpenBao:  bao_get <path> <field>
bao_get() {
  curl -s --cacert ansible/fetched/pki/ca.crt \
    -H "X-Vault-Token: $(jq -r .root_token ansible/fetched/openbao/init.json)" \
    "https://192.168.56.20:8200/v1/kv/data/$1" | jq -r ".data.data[\"$2\"]"
}
```

**Web addresses** use names ending in `.fss`. Add them to your laptop's hosts file once:
```shell
echo "192.168.56.10 grafana.fss prometheus.fss traefik.fss" | sudo tee -a /etc/hosts
```

---

## 1. Bare Kubernetes cluster

Three VMs (controlplane, node01, node02) running Kubernetes 1.36 with CRI-O, Calico, metrics-server and Helm.

**Run:**
```shell
VAGRANT_EXPERIMENTAL="disks" vagrant up
ansible-playbook ansible/site.yml --tags init
```

**Check:**
```shell
export KUBECONFIG=$PWD/ansible/fetched/admin.conf
kubectl get nodes            # 3 nodes, all Ready
kubectl get pods -A          # everything Running
kubectl top nodes            # metrics-server works (may take a minute)
```

The control plane also backs up the etcd encryption key to
`ansible/fetched/kubernetes/etcd-encryption-key.b64` with mode `0600`. Keep an offline
copy with the etcd snapshots: a restored snapshot needs its matching key. If rebuilding
the control plane, restore this file to that path before running Ansible; the role reuses
it automatically.

---

## 2. Storage

Gives apps persistent volumes. Pick a backend first.

| `storage_backend` | Use when |
|---|---|
| `local-path` (inventory default) | Lightest option; data stays on the node running the pod. |
| `longhorn` | Replicated storage that can survive losing a worker. Raise worker memory to at least `4096` MB in `hosts.yml`. |
| `nfs` | You run the services VM (section 9 must be on first). |

Select the backend in `hosts.yml`:
```yaml
storage_backend: longhorn     # or local-path / nfs
```

**Run:**
```shell
ansible-playbook ansible/site.yml --tags role_storage
```
For Longhorn, run `--tags init` first; the common role installs iSCSI on every node.

**Check:**
```shell
kubectl get storageclass                    # your backend, marked (default)
kubectl -n longhorn-system get pods         # Longhorn only: all Running
```

**Test a volume:**
```shell
kubectl create namespace storage-test
kubectl -n storage-test apply -f - <<'EOF'
apiVersion: v1
kind: PersistentVolumeClaim
metadata: { name: test }
spec: { accessModes: [ReadWriteOnce], resources: { requests: { storage: 1Gi } } }
EOF
kubectl -n storage-test get pvc test        # Longhorn: Bound. local-path binds when a pod uses it.
kubectl delete namespace storage-test
```

**Open the Longhorn UI:**
```shell
kubectl -n longhorn-system port-forward svc/longhorn-frontend 8080:80
# then browse to http://localhost:8080
```

---

## 3. Kyverno (admission policies)

Rejects privileged containers, workloads in the `default` namespace, and pods that mount NFS directly.

**Run:**
```shell
ansible-playbook ansible/site.yml --tags role_kyverno
```

**Check:**
```shell
kubectl get clusterpolicy                    # policies listed, READY True

# should be REJECTED (default namespace):
kubectl run test --image=nginx:1.27

# should be REJECTED (privileged):
kubectl create namespace policy-test
kubectl -n policy-test run priv --image=nginx:1.27 \
  --overrides='{"spec":{"containers":[{"name":"priv","image":"nginx:1.27","securityContext":{"privileged":true}}]}}'
kubectl delete namespace policy-test
```

**Change which policies are on:** edit `kyverno_policies` in
`ansible/inventories/lab/group_vars/all/main.yml`, then run `--tags role_kyverno` again.

---

## 4. Secrets (OpenBao + External Secrets)

Creates the **secrets VM** (192.168.56.20) running OpenBao, and installs External Secrets in the cluster.
Every password is generated by OpenBao. Traefik, Jenkins, Grafana, MySQL and the services VM need this.

Set `secrets_vm_enabled: true` in `hosts.yml` to include the optional secrets VM.

**Run:**
```shell
VAGRANT_EXPERIMENTAL="disks" vagrant up secrets
ansible-playbook ansible/site.yml --tags role_openbao_server
ansible-playbook ansible/site.yml --tags role_external_secrets
```

**Back up the break-glass files right away.** Copy these to a password manager:
- `ansible/fetched/openbao/unseal-key.b64`: **losing it loses every secret**
- `ansible/fetched/openbao/init.json`: root token and recovery key

**Check:**
```shell
curl -s --cacert ansible/fetched/pki/ca.crt https://192.168.56.20:8200/v1/sys/health | jq '{initialized, sealed}'
# -> initialized: true, sealed: false

kubectl get clustersecretstore openbao        # STATUS Valid, READY True

bao_get bootstrap/traefik dashboard-password  # prints a 32-character password
```

**Open the OpenBao UI:** https://192.168.56.20:8200. Your browser will warn about the lab CA; you can
import `ansible/fetched/pki/ca.crt` to stop the warning. Log in with the token from:
```shell
jq -r .root_token ansible/fetched/openbao/init.json
```

---

## 5. Traefik (ingress + dashboard)

Routes `*.fss` web traffic to apps and serves a password-protected dashboard.

**Needs:** OpenBao only when `traefik_dashboard_enabled: true` (the default). Set it to `false` to install Traefik without the OpenBao-backed dashboard.

**Run:**
```shell
ansible-playbook ansible/site.yml --tags role_traefik
```

**Check and open:**
```shell
kubectl -n traefik get pods                   # Running
bao_get bootstrap/traefik dashboard-password  # the dashboard password
```
Browse to **http://traefik.fss:30090/dashboard/** and log in as `admin`.

---

## 6. Jenkins

**Needs:** a StorageClass and OpenBao/External Secrets for its admin password.

**Run:**
```shell
ansible-playbook ansible/site.yml --tags role_jenkins
```

**Check and open:**
```shell
kubectl -n jenkins get pods,pvc               # pod Running, PVC Bound
bao_get apps/jenkins admin-password           # the admin password
```
Browse to **http://192.168.56.10:32000** and log in as `admin`.

---

## 7. Monitoring (Prometheus + Grafana)

Prometheus and Grafana can be run independently and in either order. Grafana can start before Prometheus; its datasource will connect when Prometheus is available. Both use persistent volumes and therefore need a StorageClass. Grafana also needs External Secrets and OpenBao for its admin password. Ingress is enabled by default; set `prometheus_ingress_enabled: false` or `grafana_ingress_enabled: false` to install either role without Traefik. Without ingress, use `kubectl port-forward` or configure another way to reach the service.

For example, to install both without Traefik:
```shell
ansible-playbook ansible/site.yml --tags role_prometheus -e prometheus_ingress_enabled=false
ansible-playbook ansible/site.yml --tags role_grafana -e grafana_ingress_enabled=false
kubectl -n monitoring port-forward svc/prometheus-server 9090:80
# In a second terminal:
kubectl -n monitoring port-forward svc/grafana 3000:80
```

**Run:**
```shell
ansible-playbook ansible/site.yml --tags role_prometheus
ansible-playbook ansible/site.yml --tags role_grafana
```

**Check and open:**
```shell
kubectl -n monitoring get pods,pvc            # all Running, PVCs Bound
bao_get apps/grafana admin-password           # Grafana admin password
```
- Prometheus: **http://prometheus.fss:30090**
- Grafana: **http://grafana.fss:30090**, user `admin`. Prometheus is already set as the data source.

---

## 8. MySQL

**Needs:** a StorageClass and OpenBao/External Secrets for its database credentials.

**Run:**
```shell
ansible-playbook ansible/site.yml --tags role_mysql
```

**Check:**
```shell
kubectl -n mysql get statefulset,pvc                      # mysql 1/1, PVC Bound
kubectl -n taskmanager get secret streamlit-mysql-secret  # your app's credentials exist
```

**Connect:**
```shell
bao_get apps/mysql password                   # the appuser password
kubectl -n mysql exec -it mysql-0 -- mysql -uappuser -p appdb
```
From inside the cluster, apps connect to `mysql.mysql.svc.cluster.local:3306`.

---

## 9. Services VM (NFS, GitLab, Gitea, Nexus, Harbor)

**Needs:** Docker on the services VM (installed by `role_docker_nfs`) and OpenBao for Harbor's admin password. Uses about 3 GB of RAM.
Set `services_vm_enabled: true` in `hosts.yml` to include the optional services VM.

**Run:**
```shell
VAGRANT_EXPERIMENTAL="disks" vagrant up services
ansible-playbook ansible/site.yml --tags role_docker_nfs,role_docker_insecure_registry,role_gitlab,role_gitea,role_nexus,role_harbor
```

**Open each service:**

| Service | URL | First login |
|---|---|---|
| GitLab | http://192.168.56.80 | `root`, password from `vagrant ssh services -c "sudo docker exec gitlab cat /etc/gitlab/initial_root_password"` (the file is deleted after 24 h) |
| Gitea | http://192.168.56.80:3000 | Finish the setup page and create your admin user |
| Nexus | http://192.168.56.80:8081 | `admin`, password from `vagrant ssh services -c "sudo cat /srv/nexus/admin.password"` |
| Harbor | http://192.168.56.80:8880 | `admin`, password from `bao_get bootstrap/harbor admin-password` |

**Check NFS:**
```shell
vagrant ssh services -c "sudo exportfs -v"    # /srv/nfs/k8s exported only to the three Kubernetes node IPs
```
To use it as cluster storage, set `storage_backend: nfs` (section 2).

---

## Everyday commands

| To | Run |
|---|---|
| Stop everything (frees RAM and CPU) | `vagrant halt` |
| Pause and resume quickly | `vagrant suspend`, later `vagrant resume` |
| Start again | `vagrant up` |
| Rebuild the cluster, **keep all secrets** | `vagrant destroy -f controlplane node01 node02 && vagrant up`, then the playbook |
| Destroy everything | `vagrant destroy -f` |
| Re-run only the cluster foundation | `ansible-playbook site.yml --tags init` |
| Preview a role | `ansible-playbook site.yml --tags role_prometheus --check --diff` (some tasks can't predict changes) |

## Running roles

Run one role with its `role_*` tag. Dependencies are not started implicitly, and rerunning a role reconciles its resources without uninstalling them. To remove a
component, uninstall its Helm release or remove its Kubernetes resources explicitly.

## Troubleshooting

| Symptom | Look at |
|---|---|
| The run stops at storage preflight | Choose `longhorn`, `local-path`, or `nfs`; NFS requires the services VM to exist. |
| A role fails at "Validating arguments" | The variable named in the error is missing or misspelled. |
| `vagrant up` doesn't create the secrets or services VM | Check `secrets_vm_enabled` and `services_vm_enabled` in `hosts.yml`. |
| ExternalSecret not syncing | `kubectl describe clustersecretstore openbao`, then `vagrant ssh secrets -c "sudo tail /var/log/openbao/audit.log"` |
| Longhorn volume stuck attaching | `vagrant ssh node01 -c "systemctl status iscsid"` |
| Can't reach `*.fss` | The `/etc/hosts` line from section 0, and `kubectl -n traefik get pods` |
| Laptop is slow | `vagrant halt` what you're not using; see the RAM notes in section 2 |
