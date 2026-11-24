# Example configurations

Role execution is explicit: use a Kuboos task template or the matching `role_*` Ansible tag. The settings below only describe optional VM topology and storage.

## Base Kubernetes cluster

```yaml
services_vm_enabled: false
secrets_vm_enabled: false
storage_backend: local-path
```

Run the base roles with `ansible-playbook ansible/site.yml --tags init`.

## Optional service VMs

```yaml
services_vm_enabled: true
secrets_vm_enabled: true
storage_backend: local-path
```

After `vagrant up`, run the needed roles individually. For example, run `role_openbao_server`, then `role_external_secrets`, then `role_traefik`.

## Storage backend choices

```yaml
storage_backend: local-path
```

Or use `longhorn` for replicated storage. Run the `init` roles first so the nodes have the Longhorn prerequisites.

```yaml
services_vm_enabled: true
storage_backend: nfs
```

NFS requires the services VM. Run `role_docker_nfs` on that VM, then run `role_storage` on the control plane.

## Role tags

| Role | Tag |
|---|---|
| Common, controlplane, worker, waiting | `role_common`, `role_controlplane`, `role_worker`, `role_waiting` |
| Helm, metrics-server | `role_helm`, `role_metrics_server` |
| OpenBao, External Secrets | `role_openbao_server`, `role_external_secrets` |
| Storage, Kyverno, Traefik | `role_storage`, `role_kyverno`, `role_traefik` |
| Jenkins, Prometheus, Grafana, MySQL | `role_jenkins`, `role_prometheus`, `role_grafana`, `role_mysql` |
| Docker/NFS, Docker registry, GitLab, Gitea, Nexus, Harbor | `role_docker_nfs`, `role_docker_insecure_registry`, `role_gitlab`, `role_gitea`, `role_nexus`, `role_harbor` |

For example, run only Prometheus with `ansible-playbook ansible/site.yml --tags role_prometheus`.
