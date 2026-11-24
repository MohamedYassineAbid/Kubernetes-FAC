# Kubernetes-FAC Runbook

Step-by-step instructions to turn on each feature, check that it works, and open it.
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

**Every feature is switched on in one file:** `ansible/inventories/lab/hosts.yml`. Each section below
says which switch to change. After changing it, run the playbook again; parts that are already built are left alone.

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

**Switch:** none. This is what you get with every `deploy_*` switch set to `false`.

**Run:**
```shell
VAGRANT_EXPERIMENTAL="disks" vagrant up
cd ansible && ansible-playbook site.yml && cd ..
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

**Switch:** in `hosts.yml`
```yaml
deploy_storage: true
storage_backend: longhorn     # or local-path / nfs
```

**Run:**
```shell
cd ansible && ansible-playbook site.yml && cd ..
```
For Longhorn the full run matters: it also installs iSCSI on every node (the `common` role).

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

**Switch:** `deploy_kyverno: true`

**Run:**
```shell
cd ansible && ansible-playbook site.yml --tags kyverno && cd ..
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
`ansible/inventories/lab/group_vars/all/main.yml`, then run `--tags kyverno` again.

---

## 4. Secrets (OpenBao + External Secrets)

Creates the **secrets VM** (192.168.56.20) running OpenBao, and installs External Secrets in the cluster.
Every password is generated by OpenBao. Traefik, Jenkins, Grafana, MySQL and the services VM need this.

**Switch:** `deploy_secrets: true`

**Run:**
```shell
VAGRANT_EXPERIMENTAL="disks" vagrant up secrets
cd ansible && ansible-playbook site.yml && cd ..
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

**Needs:** secrets (section 4)
**Switch:** `deploy_traefik: true`

**Run:**
```shell
cd ansible && ansible-playbook site.yml --tags traefik && cd ..
```

**Check and open:**
```shell
kubectl -n traefik get pods                   # Running
bao_get bootstrap/traefik dashboard-password  # the dashboard password
```
Browse to **http://traefik.fss:30090/dashboard/** and log in as `admin`.

---

## 6. Jenkins

**Needs:** storage and secrets
**Switch:** `deploy_jenkins: true`

**Run:**
```shell
cd ansible && ansible-playbook site.yml --tags jenkins && cd ..
```

**Check and open:**
```shell
kubectl -n jenkins get pods,pvc               # pod Running, PVC Bound
bao_get apps/jenkins admin-password           # the admin password
```
Browse to **http://192.168.56.10:32000** and log in as `admin`.

---

## 7. Monitoring (Prometheus + Grafana)

**Needs:** storage, secrets, and Traefik. Set `deploy_traefik: true` and `deploy_monitoring: true` together; the preflight rejects monitoring if Traefik is disabled. The command below installs Traefik before the monitoring charts.
**Switch:** `deploy_monitoring: true`

**Run:**
```shell
cd ansible && ansible-playbook site.yml --tags traefik,prometheus,grafana && cd ..
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

**Needs:** storage and secrets
**Switch:** `deploy_mysql: true`

**Run:**
```shell
cd ansible && ansible-playbook site.yml --tags mysql && cd ..
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

**Needs:** secrets (Harbor's password is in OpenBao). Uses about 3 GB of RAM.
**Switch:** `services_vm_enabled: true`

**Run:**
```shell
VAGRANT_EXPERIMENTAL="disks" vagrant up services
cd ansible && ansible-playbook site.yml && cd ..
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
| See what a run would change | `ansible-playbook site.yml --check --diff` (some tasks can't predict changes) |

## Turning a feature off

Setting a switch back to `false` stops the playbook from managing that feature. It does **not**
uninstall what is already running. To remove one, delete it by hand, for example
`helm -n jenkins uninstall jenkins` from the control plane, or rebuild the cluster.

## Troubleshooting

| Symptom | Look at |
|---|---|
| The run stops at "Check that every enabled layer has what it needs" | A switch is on without its dependency. The message names it. |
| A role fails at "Validating arguments" | The variable named in the error is missing or misspelled. |
| `vagrant up` doesn't create the secrets or services VM | The switch is still `false` in `hosts.yml`. |
| ExternalSecret not syncing | `kubectl describe clustersecretstore openbao`, then `vagrant ssh secrets -c "sudo tail /var/log/openbao/audit.log"` |
| Longhorn volume stuck attaching | `vagrant ssh node01 -c "systemctl status iscsid"` |
| Can't reach `*.fss` | The `/etc/hosts` line from section 0, and `kubectl -n traefik get pods` |
| Laptop is slow | `vagrant halt` what you're not using; see the RAM notes in section 2 |
