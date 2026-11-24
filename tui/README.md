# Kubernetes-FAC Terminal UI

A terminal interface for managing Kubernetes-FAC VM topology and cluster status.

## Features

- 📝 **Configuration Editor** - Edit cluster topology, IPs, resources, and optional VM presence
- 🚀 **Deployment Control** - Start VMs and configure the base cluster with live log streaming
- 📊 **Status Dashboard** - View VM states and Kubernetes node status
- ⌨️  **Keyboard Navigation** - Full keyboard support for productivity
- 🎨 **Clean Interface** - Organized tabs and color-coded output

## Installation

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the TUI:
   ```bash
   cd /home/abid/Kubernetes-FAC/tui
   python k8s_fac_tui.py
   ```

Set `KFAC_ENV` to select another inventory (defaults to `lab`), for example:
```bash
KFAC_ENV=lab python k8s_fac_tui.py
```

   Or make it executable:
   ```bash
   chmod +x k8s_fac_tui.py
   ./k8s_fac_tui.py
   ```

## Usage

### Tabs

- **Configuration** - Edit `hosts.yml` settings visually
  - Modify node IP addresses
  - Set whether optional services and secrets VMs are part of the lab topology
  - Save changes back to the inventory files

- **Services** - Configure Services VM applications
  - **GitLab** - HTTP/SSH/Registry ports, data directory, workers
  - **Nexus** - HTTP port, data path, Docker registry (port 5002)
  - **Gitea** - HTTP/SSH ports, data path
  - **Harbor** - HTTP port, install directory, data volume
  - **NFS** - Export path for cluster storage
  - All changes save to `roles/*/defaults/main.yml` files

- **Deploy** - Execute deployment commands
  - `Vagrant Up` - Create/start VMs
  - `Set Up Cluster` - Run the `init` roles only
  - `Destroy VMs` - Clean up all VMs
  - Real-time log output for all commands

- **Status** - Monitor cluster health
  - VM states (from `vagrant status`)
  - Kubernetes node status (from `kubectl get nodes`)
  - Refresh on demand

### Keyboard Shortcuts

- `Tab` / `Shift+Tab` - Navigate between elements
- `Enter` - Activate buttons
- `Space` - Toggle a VM topology setting
- `q` - Quit application
- `r` - Refresh status
- `Ctrl+C` - Force quit

## Architecture

The TUI is a thin wrapper around the existing Vagrant/Ansible setup:

- Reads/writes `ansible/inventories/$KFAC_ENV/hosts.yml` (defaults to `lab`)
- Executes shell commands (`vagrant`, `ansible-playbook`, `kubectl`)
- Streams command output in real-time using async subprocess
- Parses status from command outputs

**No changes to your existing workflow** - you can still edit files manually and run commands directly. The TUI is just a convenience layer.

## Requirements

- Python 3.8+
- Textual >= 0.47.0
- PyYAML >= 6.0
- Rich >= 13.0.0
- Vagrant and Ansible must be in PATH

## Troubleshooting

**TUI shows "No kubeconfig found"**
- Run the Ansible playbook first - it fetches the kubeconfig to `ansible/fetched/admin.conf`

**Command buttons don't work**
- Ensure you're running the TUI from the `tui/` directory or it can find the base path
- Check that vagrant/ansible are in your PATH

**Status refresh shows empty tables**
- VMs must be running for `vagrant status` to show useful info
- Kubeconfig must exist for kubectl commands to work
