# TUI Changelog

## Version 1.1.0 - Services Configuration Added

### New Features

- ✨ **New "Services" tab** - Configure all Services VM applications
  - GitLab settings (ports, workers, data directory)
  - Nexus configuration (port, data path)
  - Gitea settings (HTTP/SSH ports, data path)
  - Harbor configuration (port, directories)
  - NFS export path
  
- 📍 **Access URLs displayed** - Shows direct links for each service based on configured ports
  - Example: `http://192.168.56.80` for GitLab
  - Updates dynamically when you change ports
  
- 💾 **Service config persistence** - Saves to individual role defaults files
  - `ansible/roles/gitlab/defaults/main.yml`
  - `ansible/roles/nexus/defaults/main.yml`
  - `ansible/roles/gitea/defaults/main.yml`
  - `ansible/roles/harbor/defaults/main.yml`

### Documentation

- 📚 Added `SERVICES_REFERENCE.md` - Complete guide to all services
  - Port reference table
  - First login credentials
  - Common workflows
  - Troubleshooting tips

### Tabs Order

1. Configuration - Cluster topology and feature toggles
2. **Services** - Services VM application settings (NEW)
3. Deploy - Command execution with live logs
4. Status - VM and cluster health monitoring

---

## Version 1.0.0 - Initial Release

### Core Features

- 📝 Configuration editor for cluster topology
- 🚀 Deployment control with live command output
- 📊 Status dashboard for VMs and Kubernetes nodes
- ⌨️  Full keyboard navigation
- 🎨 Color-coded terminal UI using Textual framework

### Tabs

1. Configuration
2. Deploy
3. Status
