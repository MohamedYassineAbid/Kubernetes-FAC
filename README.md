
# Vagrantfile and ansible scripts to automated the creation of kaggle clone

## Prerequisites

1. Working Vagrant setup
2. 8 Gig + RAM workstation as the Vms use 3 vCPUS and 4+ GB RAM

## For MAC/Linux Users

The latest version of Virtualbox for Mac/Linux can cause issues.

Create/edit the /etc/vbox/networks.conf file and add the following to avoid any network-related issues.
<pre>* 0.0.0.0/0 ::/0</pre>

or run below commands

```shell
sudo mkdir -p /etc/vbox/
echo "* 0.0.0.0/0 ::/0" | sudo tee -a /etc/vbox/networks.conf
```

So that the host only networks can be in any range, not just 192.168.56.0/21 .

## Bring Up the Cluster

To provision the cluster, execute the following commands.

```shell
VAGRANT_EXPERIMENTAL="disks" vagrant up          # VMs come from ansible/inventories/lab/hosts.yml
cd ansible && ansible-playbook site.yml
```


## To shutdown the cluster,

```shell
vagrant halt
```

## To restart the cluster,

```shell
vagrant up
```

## To destroy the cluster,

```shell
vagrant destroy -f
```

## Step-by-step guides

- **[docs/RUNBOOK.md](docs/RUNBOOK.md)**: how to turn on, check and open each feature.
- **[docs/kubernetes-fac-guide.pdf](docs/kubernetes-fac-guide.pdf)**: the full guide to the repo, with diagrams.

## What gets built

`ansible/inventories/lab/hosts.yml` decides. By default it builds a bare Kubernetes cluster (three VMs). Turn on more with the `deploy_*` switches and re-run `ansible-playbook site.yml`; parts already built are left alone.

| Switch | Adds | Needs |
|---|---|---|
| `deploy_storage` + `storage_backend` | Default StorageClass: `longhorn` (replicated), `local-path` or `nfs` | `nfs` needs the services VM |
| `deploy_kyverno` | Admission policies | |
| `deploy_secrets` | The **secrets VM** (OpenBao) and External Secrets in the cluster | |
| `deploy_traefik` | Ingress and its dashboard | secrets |
| `deploy_jenkins`, `deploy_monitoring`, `deploy_mysql` | The apps | storage, secrets |
| `services_vm_enabled` | Services VM: NFS, GitLab, Gitea, Nexus, Harbor | secrets |

Run `vagrant up` again after turning on `deploy_secrets` or `services_vm_enabled`, so the extra VM gets created.

## Where configuration and secrets live

Every value is defined once. Everything else references it. There are no secrets in git and no Ansible Vault.

| What | Where |
|---|---|
| Nodes, IPs, CPU/RAM/disk, box, deploy switches | `ansible/inventories/<env>/hosts.yml` (also read by the Vagrantfile; `KFAC_ENV` picks the env, default `lab`) |
| Settings shared by several roles | `ansible/inventories/<env>/group_vars/all/main.yml` |
| Every pinned version | `ansible/inventories/<env>/group_vars/all/versions.yml` |
| A role's own tunables | `ansible/roles/<role>/defaults/main.yml` |
| **Every secret** | **OpenBao on the secrets VM** (10.0.0.20, outside the cluster). It generates each password on first run. |

How secrets are used:

- **Pods** get theirs from the External Secrets Operator, which logs in to OpenBao with its Kubernetes ServiceAccount and can only read `kv/apps/*`.
- **Ansible** reads the Traefik and Harbor passwords (`kv/bootstrap/*`) with its own AppRole and 15-minute tokens.
- **TLS:** OpenBao serves HTTPS with a certificate from a small local CA in `ansible/fetched/pki/`.

### Break-glass files (keep them safe, never commit them)

`ansible/fetched/` is git-ignored; keys, tokens and the kubeconfig are mode 0600:

- `openbao/init.json`: root token and recovery key.
- `openbao/unseal-key.b64`: the auto-unseal key. **Losing it loses every secret.**
- `openbao/ansible-approle.json`: Ansible's read-only login.
- `pki/`: the CA and the OpenBao certificate.
- `admin.conf`: cluster-admin kubeconfig.

### Reading a secret

```shell
export BAO_ADDR=https://10.0.0.20:8200 BAO_CACERT=ansible/fetched/pki/ca.crt
export BAO_TOKEN=$(jq -r .root_token ansible/fetched/openbao/init.json)   # break-glass
bao kv get kv/apps/grafana
```

Rebuilding the cluster keeps every secret: `vagrant destroy -f controlplane node01 node02` leaves the secrets VM untouched.
