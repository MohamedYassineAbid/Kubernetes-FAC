#!/usr/bin/env python3
"""
Kubernetes-FAC TUI - Terminal UI for managing the cluster deployment
"""
import asyncio
import os
import subprocess
import yaml
from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Header, Footer, Button, Static, Input, Switch, 
    Label, Log, TabbedContent, TabPane, DataTable
)
from textual.binding import Binding
from textual.reactive import reactive


# Paths relative to the selected inventory environment.
BASE_DIR = Path(__file__).parent.parent
ANSIBLE_DIR = BASE_DIR / "ansible"
ENVIRONMENT = os.environ.get("KFAC_ENV", "lab")
INVENTORY_DIR = ANSIBLE_DIR / "inventories" / ENVIRONMENT
INVENTORY_FILE = INVENTORY_DIR / "hosts.yml"
MAIN_VARS_FILE = INVENTORY_DIR / "group_vars/all/main.yml"

# Service role defaults
SERVICE_DEFAULTS = {
    'gitlab': ANSIBLE_DIR / "roles/gitlab/defaults/main.yml",
    'nexus': ANSIBLE_DIR / "roles/nexus/defaults/main.yml",
    'gitea': ANSIBLE_DIR / "roles/gitea/defaults/main.yml",
    'harbor': ANSIBLE_DIR / "roles/harbor/defaults/main.yml",
}


class ClusterConfig:
    """Handles reading and writing cluster configuration"""
    
    def __init__(self):
        self.hosts_data = {}
        self.vars_data = {}
        self.service_configs = {}
        self.load()
    
    def load(self):
        """Load configuration from YAML files"""
        if INVENTORY_FILE.exists():
            with open(INVENTORY_FILE) as f:
                self.hosts_data = yaml.safe_load(f)
        
        if MAIN_VARS_FILE.exists():
            with open(MAIN_VARS_FILE) as f:
                self.vars_data = yaml.safe_load(f)
        
        # Load service configurations
        for service, path in SERVICE_DEFAULTS.items():
            if path.exists():
                with open(path) as f:
                    self.service_configs[service] = yaml.safe_load(f)
    
    def save_hosts(self):
        """Save hosts.yml"""
        with open(INVENTORY_FILE, 'w') as f:
            yaml.dump(self.hosts_data, f, default_flow_style=False, sort_keys=False)
    
    def save_vars(self):
        """Save main.yml"""
        with open(MAIN_VARS_FILE, 'w') as f:
            yaml.dump(self.vars_data, f, default_flow_style=False, sort_keys=False)
    
    def save_service_config(self, service: str):
        """Save a specific service configuration"""
        path = SERVICE_DEFAULTS.get(service)
        if path and service in self.service_configs:
            with open(path, 'w') as f:
                yaml.dump(self.service_configs[service], f, default_flow_style=False, sort_keys=False)
    
    def get_node_ip(self, node_name: str) -> str:
        """Get IP for a specific node"""
        try:
            nodes = self.hosts_data['all']['children']['vms']['children']['k8s_cluster']['children']
            for group in ['control_nodes', 'workers']:
                if node_name in nodes[group]['hosts']:
                    return nodes[group]['hosts'][node_name]['internal_ip']
            
            # Check secrets and service nodes
            secrets = self.hosts_data['all']['children']['vms']['children'].get('secrets_nodes', {})
            if node_name in secrets.get('hosts', {}):
                return secrets['hosts'][node_name]['internal_ip']
            
            services = self.hosts_data['all']['children']['vms']['children'].get('service_nodes', {})
            if node_name in services.get('hosts', {}):
                return services['hosts'][node_name]['internal_ip']
        except KeyError:
            pass
        return ""
    
    def set_node_ip(self, node_name: str, ip: str):
        """Set IP for a specific node"""
        try:
            nodes = self.hosts_data['all']['children']['vms']['children']['k8s_cluster']['children']
            for group in ['control_nodes', 'workers']:
                if node_name in nodes[group]['hosts']:
                    nodes[group]['hosts'][node_name]['internal_ip'] = ip
                    return
            
            # Check secrets and service nodes
            secrets = self.hosts_data['all']['children']['vms']['children'].get('secrets_nodes', {})
            if node_name in secrets.get('hosts', {}):
                secrets['hosts'][node_name]['internal_ip'] = ip
                return
            
            services = self.hosts_data['all']['children']['vms']['children'].get('service_nodes', {})
            if node_name in services.get('hosts', {}):
                services['hosts'][node_name]['internal_ip'] = ip
        except KeyError:
            pass
    
    def get_topology_setting(self, setting: str) -> bool:
        """Get optional VM topology setting"""
        return self.hosts_data['all']['vars'].get(setting, False)
    
    def set_topology_setting(self, setting: str, value: bool):
        """Set optional VM topology setting"""
        self.hosts_data['all']['vars'][setting] = value


class ConfigPanel(VerticalScroll):
    """Configuration editing panel"""
    
    def __init__(self):
        super().__init__()
        self.config = ClusterConfig()
    
    def compose(self) -> ComposeResult:
        yield Static("🔧 Cluster Configuration", classes="section-title")
        
        # Network section
        yield Static("Network Settings", classes="subsection-title")
        yield Horizontal(
            Label("Network CIDR:", classes="label"),
            Input(
                value=self.config.hosts_data['all']['vars'].get('private_network_cidr', '192.168.56.0/24'),
                placeholder="192.168.56.0/24",
                id="network_cidr"
            ),
            classes="config-row"
        )
        yield Horizontal(
            Label("Storage backend:", classes="label"),
            Input(
                value=self.config.hosts_data['all']['vars'].get('storage_backend', 'local-path'),
                placeholder="local-path, longhorn, or nfs",
                id="storage_backend"
            ),
            classes="config-row"
        )
        
        # Node IPs
        yield Static("Node IP Addresses", classes="subsection-title")
        for node in ["controlplane", "node01", "node02"]:
            yield Horizontal(
                Label(f"{node}:", classes="label"),
                Input(
                    value=self.config.get_node_ip(node),
                    placeholder="192.168.56.x",
                    id=f"ip_{node}"
                ),
                classes="config-row"
            )
        
        # Optional VM topology
        yield Static("Optional VM Topology", classes="subsection-title")
        yield Static("These settings control which VMs exist. Run application roles from Kuboos.", classes="info-message")
        
        settings = [
            ("services_vm_enabled", "Services VM (GitLab, Nexus, Harbor, NFS)"),
            ("secrets_vm_enabled", "Secrets VM (OpenBao)"),
        ]
        
        for setting_id, label in settings:
            yield Horizontal(
                Switch(value=self.config.get_topology_setting(setting_id), id=setting_id),
                Label(label, classes="switch-label"),
                classes="config-row"
            )
        
        yield Horizontal(
            Button("Save Configuration", variant="primary", id="save_config"),
            Button("Reload", variant="default", id="reload_config"),
            classes="button-row"
        )
        
        yield Static("", id="config_status")


class ServicesPanel(VerticalScroll):
    """Services VM configuration panel"""
    
    def __init__(self):
        super().__init__()
        self.config = ClusterConfig()
        self.show_info = False
    
    def compose(self) -> ComposeResult:
        yield Static("🛠️  Services VM Configuration", classes="section-title")
        
        services_enabled = self.config.get_topology_setting('services_vm_enabled')
        services_ip = self.config.get_node_ip('services') or "192.168.56.80"
        
        if not services_enabled:
            yield Static(
                "\n⚠️  Services VM is disabled. Enable 'Services VM' in Configuration tab first.\n",
                classes="warning-message"
            )
        else:
            yield Static(
                f"📍 Services VM IP: {services_ip} | Access URLs below after deployment",
                classes="info-message"
            )
        
        # GitLab Configuration
        yield Static("GitLab (Git Repository + CI/CD)", classes="subsection-title")
        gitlab = self.config.service_configs.get('gitlab', {})
        
        gitlab_http = gitlab.get('gitlab_http_port', 80)
        gitlab_ssh = gitlab.get('gitlab_ssh_port', 2222)
        
        if services_enabled:
            yield Static(
                f"→ Web: http://{services_ip}:{gitlab_http} | SSH: git@{services_ip}:{gitlab_ssh}",
                classes="access-info"
            )
        
        yield Horizontal(
            Label("HTTP Port:", classes="label"),
            Input(value=str(gitlab.get('gitlab_http_port', 80)), placeholder="80", id="gitlab_http_port"),
            classes="config-row"
        )
        yield Horizontal(
            Label("SSH Port:", classes="label"),
            Input(value=str(gitlab.get('gitlab_ssh_port', 2222)), placeholder="2222", id="gitlab_ssh_port"),
            classes="config-row"
        )
        yield Horizontal(
            Label("Registry Port:", classes="label"),
            Input(value=str(gitlab.get('gitlab_registry_port', 5050)), placeholder="5050", id="gitlab_registry_port"),
            classes="config-row"
        )
        yield Horizontal(
            Label("Data Directory:", classes="label"),
            Input(value=gitlab.get('gitlab_data_dir', '/srv/gitlab'), placeholder="/srv/gitlab", id="gitlab_data_dir"),
            classes="config-row"
        )
        yield Horizontal(
            Label("Puma Workers:", classes="label"),
            Input(value=str(gitlab.get('gitlab_puma_workers', 2)), placeholder="2", id="gitlab_puma_workers"),
            classes="config-row"
        )
        
        # Nexus Configuration
        yield Static("Nexus (Artifact Repository + Docker Registry)", classes="subsection-title")
        nexus = self.config.service_configs.get('nexus', {})
        
        nexus_http = nexus.get('nexus_http_port', 8081)
        
        if services_enabled:
            yield Static(
                f"→ Web: http://{services_ip}:{nexus_http} | Registry: {services_ip}:5002",
                classes="access-info"
            )
        
        yield Horizontal(
            Label("HTTP Port:", classes="label"),
            Input(value=str(nexus.get('nexus_http_port', 8081)), placeholder="8081", id="nexus_http_port"),
            classes="config-row"
        )
        yield Horizontal(
            Label("Data Path:", classes="label"),
            Input(value=nexus.get('nexus_data_path', '/srv/nexus'), placeholder="/srv/nexus", id="nexus_data_path"),
            classes="config-row"
        )
        
        # Gitea Configuration
        yield Static("Gitea (Lightweight Git Service)", classes="subsection-title")
        gitea = self.config.service_configs.get('gitea', {})
        
        gitea_http = gitea.get('gitea_http_port', 3000)
        gitea_ssh = gitea.get('gitea_ssh_port', 2224)
        
        if services_enabled:
            yield Static(
                f"→ Web: http://{services_ip}:{gitea_http} | SSH: git@{services_ip}:{gitea_ssh}",
                classes="access-info"
            )
        
        yield Horizontal(
            Label("HTTP Port:", classes="label"),
            Input(value=str(gitea.get('gitea_http_port', 3000)), placeholder="3000", id="gitea_http_port"),
            classes="config-row"
        )
        yield Horizontal(
            Label("SSH Port:", classes="label"),
            Input(value=str(gitea.get('gitea_ssh_port', 2224)), placeholder="2224", id="gitea_ssh_port"),
            classes="config-row"
        )
        yield Horizontal(
            Label("Data Path:", classes="label"),
            Input(value=gitea.get('gitea_data_path', '/srv/gitea'), placeholder="/srv/gitea", id="gitea_data_path"),
            classes="config-row"
        )
        
        # Harbor Configuration
        yield Static("Harbor (Container Registry + Vulnerability Scanner)", classes="subsection-title")
        harbor = self.config.service_configs.get('harbor', {})
        
        harbor_http = harbor.get('harbor_http_port', 8880)
        
        if services_enabled:
            yield Static(
                f"→ Web: http://{services_ip}:{harbor_http} | Login: admin (password in OpenBao)",
                classes="access-info"
            )
        
        yield Horizontal(
            Label("HTTP Port:", classes="label"),
            Input(value=str(harbor.get('harbor_http_port', 8880)), placeholder="8880", id="harbor_http_port"),
            classes="config-row"
        )
        yield Horizontal(
            Label("Install Directory:", classes="label"),
            Input(value=harbor.get('harbor_install_dir', '/opt/harbor'), placeholder="/opt/harbor", id="harbor_install_dir"),
            classes="config-row"
        )
        yield Horizontal(
            Label("Data Volume:", classes="label"),
            Input(value=harbor.get('harbor_data_volume', '/data'), placeholder="/data", id="harbor_data_volume"),
            classes="config-row"
        )
        
        # NFS Configuration (from main.yml)
        yield Static("NFS Server (Shared Storage)", classes="subsection-title")
        
        yield Horizontal(
            Label("Export Path:", classes="label"),
            Input(value=self.config.vars_data.get('nfs_path', '/srv/nfs/k8s'), placeholder="/srv/nfs/k8s", id="nfs_path"),
            classes="config-row"
        )
        
        yield Horizontal(
            Button("Save Services Config", variant="primary", id="save_services"),
            Button("Reload", variant="default", id="reload_services"),
            classes="button-row"
        )
        
        yield Static("", id="services_status")


class DeployPanel(Vertical):
    """Deployment control and log panel"""
    
    def compose(self) -> ComposeResult:
        yield Static("🚀 Deployment Control", classes="section-title")
        
        yield Horizontal(
            Button("Vagrant Up", variant="success", id="vagrant_up"),
            Button("Set Up Cluster", variant="primary", id="ansible_deploy"),
            Button("Destroy VMs", variant="error", id="vagrant_destroy"),
            classes="button-row"
        )
        
        yield Static("Deployment Log", classes="subsection-title")
        yield Log(id="run_log", auto_scroll=True)


class StatusPanel(Vertical):
    """Cluster status dashboard"""
    
    vm_status = reactive("Unknown")
    cluster_status = reactive("Unknown")
    
    def compose(self) -> ComposeResult:
        yield Static("📊 Cluster Status", classes="section-title")
        
        yield Static("Virtual Machines", classes="subsection-title")
        vm_table = DataTable(id="vm_table")
        vm_table.add_columns("VM", "State", "IP")
        yield vm_table
        
        yield Static("Kubernetes Nodes", classes="subsection-title")
        node_table = DataTable(id="node_table")
        node_table.add_columns("Node", "Status", "Version", "Age")
        yield node_table
        
        yield Horizontal(
            Button("Refresh Status", variant="primary", id="refresh_status"),
            classes="button-row"
        )


class KubernetesFACTUI(App):
    """Main TUI Application"""
    
    CSS = """
    Screen {
        background: $surface;
    }
    
    .section-title {
        background: $primary;
        color: $text;
        padding: 1;
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }
    
    .subsection-title {
        background: $panel;
        color: $text;
        padding: 0 1;
        text-style: bold;
        margin-top: 1;
        margin-bottom: 1;
    }
    
    .config-row {
        height: auto;
        padding: 0 2;
        margin-bottom: 1;
    }
    
    .label {
        width: 30;
        padding-top: 1;
    }
    
    .switch-label {
        width: 50;
        padding-top: 1;
        padding-left: 2;
    }
    
    .warning-message {
        background: $warning;
        color: $text;
        padding: 1 2;
        text-align: center;
    }
    
    .info-message {
        background: $panel;
        color: $accent;
        padding: 1 2;
        text-align: center;
        margin-bottom: 1;
    }
    
    .access-info {
        color: $success;
        padding: 0 2 1 2;
        text-style: italic;
    }
    
    Input {
        width: 30;
    }
    
    .button-row {
        height: auto;
        padding: 1 2;
        align: center middle;
    }
    
    Button {
        margin: 0 1;
    }
    
    Log {
        height: 100%;
        border: solid $primary;
        margin: 0 2 1 2;
    }
    
    DataTable {
        height: auto;
        margin: 0 2 1 2;
    }
    
    #config_status {
        padding: 1 2;
        color: $success;
    }
    """
    
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
    ]
    
    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            with TabPane("Configuration", id="tab_config"):
                yield ConfigPanel()
            with TabPane("Services", id="tab_services"):
                yield ServicesPanel()
            with TabPane("Deploy", id="tab_deploy"):
                yield DeployPanel()
            with TabPane("Status", id="tab_status"):
                yield StatusPanel()
        yield Footer()
    
    def on_mount(self) -> None:
        """Called when app starts"""
        self.title = "Kubernetes-FAC Cluster Manager"
        self.sub_title = f"Environment: {ENVIRONMENT} | Path: {BASE_DIR}"
    
    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button clicks"""
        button_id = event.button.id
        
        if button_id == "save_config":
            await self.save_configuration()
        elif button_id == "reload_config":
            await self.reload_configuration()
        elif button_id == "save_services":
            await self.save_services_configuration()
        elif button_id == "reload_services":
            await self.reload_services_configuration()
        elif button_id == "vagrant_up":
            await self.run_command("vagrant_up")
        elif button_id == "ansible_deploy":
            await self.run_command("ansible_deploy")
        elif button_id == "vagrant_destroy":
            await self.run_command("vagrant_destroy")
        elif button_id == "refresh_status":
            await self.refresh_status()
    
    async def save_configuration(self):
        """Save configuration from UI to YAML files"""
        config = ClusterConfig()
        
        # Update network CIDR
        network_input = self.query_one("#network_cidr", Input)
        config.hosts_data['all']['vars']['private_network_cidr'] = network_input.value
        storage_backend_input = self.query_one("#storage_backend", Input)
        config.hosts_data['all']['vars']['storage_backend'] = storage_backend_input.value.strip()
        
        # Update node IPs
        for node in ["controlplane", "node01", "node02"]:
            ip_input = self.query_one(f"#ip_{node}", Input)
            config.set_node_ip(node, ip_input.value)
        
        # Update optional VM topology settings.
        for setting in ["services_vm_enabled", "secrets_vm_enabled"]:
            setting_widget = self.query_one(f"#{setting}", Switch)
            config.set_topology_setting(setting, setting_widget.value)
        
        # Save to files
        config.save_hosts()
        
        status = self.query_one("#config_status", Static)
        status.update("✅ Configuration saved successfully!")
    
    async def reload_configuration(self):
        """Reload configuration from files"""
        config = ClusterConfig()
        self.query_one("#network_cidr", Input).value = str(config.hosts_data['all']['vars'].get('private_network_cidr', ''))
        self.query_one("#storage_backend", Input).value = str(config.hosts_data['all']['vars'].get('storage_backend', 'local-path'))
        for node in ["controlplane", "node01", "node02"]:
            self.query_one(f"#ip_{node}", Input).value = config.get_node_ip(node)
        for setting in ["services_vm_enabled", "secrets_vm_enabled"]:
            self.query_one(f"#{setting}", Switch).value = config.get_topology_setting(setting)
        self.notify("Configuration reloaded from files")
    
    async def save_services_configuration(self):
        """Save services configuration from UI to YAML files"""
        config = ClusterConfig()
        fields = {
            'gitlab': [('gitlab_http_port', int), ('gitlab_ssh_port', int), ('gitlab_registry_port', int), ('gitlab_data_dir', str), ('gitlab_puma_workers', int)],
            'nexus': [('nexus_http_port', int), ('nexus_data_path', str)],
            'gitea': [('gitea_http_port', int), ('gitea_ssh_port', int), ('gitea_data_path', str)],
            'harbor': [('harbor_http_port', int), ('harbor_install_dir', str), ('harbor_data_volume', str)],
        }
        try:
            for service, service_fields in fields.items():
                values = config.service_configs.setdefault(service, {})
                for field, field_type in service_fields:
                    raw_value = self.query_one(f"#{field}", Input).value.strip()
                    if raw_value:
                        values[field] = field_type(raw_value)
            nfs_path = self.query_one("#nfs_path", Input).value.strip()
            if nfs_path:
                config.vars_data['nfs_path'] = nfs_path
        except (ValueError, KeyError) as error:
            self.query_one("#services_status", Static).update(f"❌ Invalid setting: {error}")
            return

        config.save_vars()
        # Save all service configs
        for service in ['gitlab', 'nexus', 'gitea', 'harbor']:
            config.save_service_config(service)
        
        status = self.query_one("#services_status", Static)
        status.update("✅ Services configuration saved successfully!")
        self.notify("Services configuration saved")
    
    async def reload_services_configuration(self):
        """Reload services configuration from files"""
        config = ClusterConfig()
        fields = {
            'gitlab': ['gitlab_http_port', 'gitlab_ssh_port', 'gitlab_registry_port', 'gitlab_data_dir', 'gitlab_puma_workers'],
            'nexus': ['nexus_http_port', 'nexus_data_path'],
            'gitea': ['gitea_http_port', 'gitea_ssh_port', 'gitea_data_path'],
            'harbor': ['harbor_http_port', 'harbor_install_dir', 'harbor_data_volume'],
        }
        for service, names in fields.items():
            values = config.service_configs.get(service, {})
            for name in names:
                if name in values:
                    self.query_one(f"#{name}", Input).value = str(values[name])
        self.query_one("#nfs_path", Input).value = str(config.vars_data.get('nfs_path', ''))
        self.notify("Services configuration reloaded from files")
    
    async def run_command(self, command_type: str):
        """Run deployment commands with live output"""
        log_widget = self.query_one("#run_log", Log)
        log_widget.clear()
        
        commands = {
            "vagrant_up": {
                "cmd": 'VAGRANT_EXPERIMENTAL="disks" vagrant up',
                "cwd": BASE_DIR,
                "desc": "Starting Vagrant VMs..."
            },
            "ansible_deploy": {
                "cmd": f"ansible-playbook -i inventories/{ENVIRONMENT}/hosts.yml site.yml --tags init",
                "cwd": ANSIBLE_DIR,
                "desc": "Configuring the base Kubernetes cluster..."
            },
            "vagrant_destroy": {
                "cmd": "vagrant destroy -f",
                "cwd": BASE_DIR,
                "desc": "Destroying VMs..."
            }
        }
        
        if command_type not in commands:
            return
        
        cmd_info = commands[command_type]
        log_widget.write_line(f"[bold cyan]{cmd_info['desc']}[/bold cyan]")
        log_widget.write_line(f"[dim]Command: {cmd_info['cmd']}[/dim]")
        log_widget.write_line("")
        
        try:
            process = await asyncio.create_subprocess_shell(
                cmd_info['cmd'],
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=cmd_info['cwd'],
                env={**os.environ, "KFAC_ENV": ENVIRONMENT}
            )
            
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                log_widget.write_line(line.decode().rstrip())
            
            await process.wait()
            
            if process.returncode == 0:
                log_widget.write_line("")
                log_widget.write_line("[bold green]✅ Command completed successfully![/bold green]")
            else:
                log_widget.write_line("")
                log_widget.write_line(f"[bold red]❌ Command failed with exit code {process.returncode}[/bold red]")
        
        except Exception as e:
            log_widget.write_line(f"[bold red]Error: {str(e)}[/bold red]")
    
    async def refresh_status(self):
        """Refresh cluster status information"""
        vm_table = self.query_one("#vm_table", DataTable)
        node_table = self.query_one("#node_table", DataTable)
        
        # Clear existing rows
        vm_table.clear()
        node_table.clear()
        
        # Get Vagrant VM status
        try:
            result = subprocess.run(
                ["vagrant", "status"],
                cwd=BASE_DIR,
                capture_output=True,
                text=True,
                env={**os.environ, "KFAC_ENV": ENVIRONMENT}
            )
            
            # Parse vagrant status output
            for line in result.stdout.split('\n'):
                if any(vm in line for vm in ["controlplane", "node01", "node02", "secrets", "services"]):
                    parts = line.split()
                    if len(parts) >= 2:
                        vm_name = parts[0]
                        vm_state = parts[1]
                        config = ClusterConfig()
                        vm_ip = config.get_node_ip(vm_name)
                        vm_table.add_row(vm_name, vm_state, vm_ip)
        except Exception as e:
            vm_table.add_row("Error", str(e), "")
        
        # Get Kubernetes node status
        kubeconfig = ANSIBLE_DIR / "fetched/admin.conf"
        if kubeconfig.exists():
            try:
                result = subprocess.run(
                    ["kubectl", "get", "nodes", "--no-headers"],
                    env={**os.environ, "KUBECONFIG": str(kubeconfig)},
                    capture_output=True,
                    text=True
                )
                
                for line in result.stdout.strip().split('\n'):
                    if line:
                        parts = line.split()
                        if len(parts) >= 5:
                            node_table.add_row(parts[0], parts[1], parts[4], parts[3])
            except Exception as e:
                node_table.add_row("Error", str(e), "", "")
        else:
            node_table.add_row("No kubeconfig found", "Run ansible-playbook first", "", "")
        
        self.notify("Status refreshed")
    
    def action_refresh(self) -> None:
        """Refresh status (keyboard binding)"""
        self.run_worker(self.refresh_status())


def main():
    app = KubernetesFACTUI()
    app.run()


if __name__ == "__main__":
    main()
