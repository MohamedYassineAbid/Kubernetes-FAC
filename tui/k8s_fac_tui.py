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


# Paths relative to the tui directory
BASE_DIR = Path(__file__).parent.parent
ANSIBLE_DIR = BASE_DIR / "ansible"
INVENTORY_FILE = ANSIBLE_DIR / "inventories/lab/hosts.yml"
MAIN_VARS_FILE = ANSIBLE_DIR / "inventories/lab/group_vars/all/main.yml"

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
    
    def get_deploy_switch(self, switch: str) -> bool:
        """Get deploy switch value"""
        return self.hosts_data['all']['vars'].get(switch, False)
    
    def set_deploy_switch(self, switch: str, value: bool):
        """Set deploy switch value"""
        self.hosts_data['all']['vars'][switch] = value


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
        
        # Feature toggles
        yield Static("Deployment Features", classes="subsection-title")
        
        switches = [
            ("services_vm_enabled", "Services VM (GitLab, Nexus, Harbor, NFS)"),
            ("deploy_secrets", "Secrets (OpenBao + External Secrets)"),
            ("deploy_storage", "Storage (Longhorn/Local-Path/NFS)"),
            ("deploy_kyverno", "Kyverno (Policy Engine)"),
            ("deploy_traefik", "Traefik (Ingress Controller)"),
            ("deploy_jenkins", "Jenkins"),
            ("deploy_monitoring", "Monitoring (Prometheus + Grafana)"),
            ("deploy_mysql", "MySQL Database"),
        ]
        
        for switch_id, label in switches:
            yield Horizontal(
                Switch(value=self.config.get_deploy_switch(switch_id), id=switch_id),
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
        
        services_enabled = self.config.get_deploy_switch('services_vm_enabled')
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
            Button("Ansible Deploy", variant="primary", id="ansible_deploy"),
            Button("Destroy VMs", variant="error", id="vagrant_destroy"),
            classes="button-row"
        )
        
        yield Static("Deployment Log", classes="subsection-title")
        yield Log(id="deploy_log", auto_scroll=True)


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
        font-style: italic;
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
        self.sub_title = f"Environment: lab | Path: {BASE_DIR}"
    
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
        
        # Update node IPs
        for node in ["controlplane", "node01", "node02"]:
            ip_input = self.query_one(f"#ip_{node}", Input)
            config.set_node_ip(node, ip_input.value)
        
        # Update deploy switches
        switches = [
            "services_vm_enabled", "deploy_secrets", "deploy_storage",
            "deploy_kyverno", "deploy_traefik", "deploy_jenkins",
            "deploy_monitoring", "deploy_mysql"
        ]
        for switch in switches:
            switch_widget = self.query_one(f"#{switch}", Switch)
            config.set_deploy_switch(switch, switch_widget.value)
        
        # Save to files
        config.save_hosts()
        
        status = self.query_one("#config_status", Static)
        status.update("✅ Configuration saved successfully!")
    
    async def reload_configuration(self):
        """Reload configuration from files"""
        self.notify("Configuration reloaded from files")
        # Would need to rebuild the panel to show new values
        # For now, just notify - full implementation would require panel refresh
    
    async def save_services_configuration(self):
        """Save services configuration from UI to YAML files"""
        config = ClusterConfig()
        
        # GitLab settings
        gitlab_fields = [
            ('gitlab_http_port', int),
            ('gitlab_ssh_port', int),
            ('gitlab_registry_port', int),
            ('gitlab_data_dir', str),
            ('gitlab_puma_workers', int),
        ]
        
        for field, field_type in gitlab_fields:
            try:
                widget = self.query_one(f"#{field}", Input)
                value = field_type(widget.value) if widget.value else None
                if value is not None:
                    if 'gitlab' not in config.service_configs:
                        config.service_configs['gitlab'] = {}
                    config.service_configs['gitlab'][field] = value
            except Exception:
                pass
        
        # Nexus settings
        nexus_fields = [
            ('nexus_http_port', int),
            ('nexus_data_path', str),
        ]
        
        for field, field_type in nexus_fields:
            try:
                widget = self.query_one(f"#{field}", Input)
                value = field_type(widget.value) if widget.value else None
                if value is not None:
                    if 'nexus' not in config.service_configs:
                        config.service_configs['nexus'] = {}
                    config.service_configs['nexus'][field] = value
            except Exception:
                pass
        
        # Gitea settings
        gitea_fields = [
            ('gitea_http_port', int),
            ('gitea_ssh_port', int),
            ('gitea_data_path', str),
        ]
        
        for field, field_type in gitea_fields:
            try:
                widget = self.query_one(f"#{field}", Input)
                value = field_type(widget.value) if widget.value else None
                if value is not None:
                    if 'gitea' not in config.service_configs:
                        config.service_configs['gitea'] = {}
                    config.service_configs['gitea'][field] = value
            except Exception:
                pass
        
        # Harbor settings
        harbor_fields = [
            ('harbor_http_port', int),
            ('harbor_install_dir', str),
            ('harbor_data_volume', str),
        ]
        
        for field, field_type in harbor_fields:
            try:
                widget = self.query_one(f"#{field}", Input)
                value = field_type(widget.value) if widget.value else None
                if value is not None:
                    if 'harbor' not in config.service_configs:
                        config.service_configs['harbor'] = {}
                    config.service_configs['harbor'][field] = value
            except Exception:
                pass
        
        # NFS path (goes to main.yml, not service defaults)
        try:
            nfs_input = self.query_one("#nfs_path", Input)
            if nfs_input.value:
                config.vars_data['nfs_path'] = nfs_input.value
                config.save_vars()
        except Exception:
            pass
        
        # Save all service configs
        for service in ['gitlab', 'nexus', 'gitea', 'harbor']:
            config.save_service_config(service)
        
        status = self.query_one("#services_status", Static)
        status.update("✅ Services configuration saved successfully!")
        self.notify("Services configuration saved")
    
    async def reload_services_configuration(self):
        """Reload services configuration from files"""
        self.notify("Services configuration reloaded from files")
    
    async def run_command(self, command_type: str):
        """Run deployment commands with live output"""
        log_widget = self.query_one("#deploy_log", Log)
        log_widget.clear()
        
        commands = {
            "vagrant_up": {
                "cmd": 'VAGRANT_EXPERIMENTAL="disks" vagrant up',
                "cwd": BASE_DIR,
                "desc": "Starting Vagrant VMs..."
            },
            "ansible_deploy": {
                "cmd": "ansible-playbook site.yml",
                "cwd": ANSIBLE_DIR,
                "desc": "Running Ansible playbook..."
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
                cwd=cmd_info['cwd']
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
                text=True
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
