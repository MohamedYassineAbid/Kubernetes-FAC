require "yaml"
require "shellwords"

# Everything comes from the Ansible inventory (single source of truth).
# KFAC_ENV picks the environment: ansible/inventories/<env>/hosts.yml (default: lab)
KFAC_ENV  = ENV.fetch("KFAC_ENV", "lab")
INVENTORY = YAML.load_file(File.join(__dir__, "ansible", "inventories", KFAC_ENV, "hosts.yml"))
ALL_VARS  = INVENTORY["all"].fetch("vars", {})

CLUSTER_NAME = ALL_VARS.fetch("cluster_name", "")
BOX          = ALL_VARS.fetch("vagrant_box")

def collect_hosts(group, acc = {})
  (group["hosts"] || {}).each { |name, vars| acc[name] = vars || {} }
  (group["children"] || {}).each_value { |child| collect_hosts(child || {}, acc) }
  acc
end

# Find a group by name anywhere in the inventory tree
def find_group(group, name)
  (group["children"] || {}).each do |child_name, child|
    return child || {} if child_name == name
    found = find_group(child || {}, name)
    return found if found
  end
  nil
end

NODES = collect_hosts(INVENTORY["all"])
SHARED_SSH_KEY_PATH = File.join(__dir__, ".vagrant", "kuboos_shared_key.pub")
SHARED_SSH_KEY = File.file?(SHARED_SSH_KEY_PATH) ? File.read(SHARED_SSH_KEY_PATH).strip : nil

# Optional VMs, selected by topology settings in hosts.yml: group => setting
{ "service_nodes" => "services_vm_enabled", "secrets_nodes" => "secrets_vm_enabled" }.each do |group, setting|
  next if ALL_VARS.fetch(setting, false)
  collect_hosts(find_group(INVENTORY["all"], group) || {}).each_key { |h| NODES.delete(h) }
end

Vagrant.configure("2") do |config|

  if `uname -m`.strip == "aarch64"
    config.vm.box = BOX + "-arm64"
  else
    config.vm.box = BOX
  end
  config.vm.box_check_update = true

  config.ssh.insert_key = true

  NODES.each do |name, vars|
    config.vm.define name do |node|
      node.vm.hostname = name
      node.vm.network "private_network", ip: vars.fetch("internal_ip")
      # Primary disk size (e.g. "60GB"); only grows, never shrinks.
      # Requires: VAGRANT_EXPERIMENTAL="disks" vagrant up
      if vars["vm_disk"]
        node.vm.disk :disk, size: vars["vm_disk"], primary: true
      end
      node.vm.provider "virtualbox" do |vb|
        vb.cpus   = vars.fetch("vm_cpus", 2)
        vb.memory = vars.fetch("vm_memory", 2048)
        if CLUSTER_NAME != ""
          vb.customize ["modifyvm", :id, "--groups", ("/" + CLUSTER_NAME)]
        end
      end

      # Add the project-local Kuboos key to every VM, while retaining Vagrant's
      # per-machine key. The public key is kept under ignored .vagrant/ state.
      if SHARED_SSH_KEY && !SHARED_SSH_KEY.empty?
        escaped_key = Shellwords.escape(SHARED_SSH_KEY)
        node.vm.provision "shell", inline: <<~SHELL
          set -eu
          install -d -m 700 -o vagrant -g vagrant /home/vagrant/.ssh
          touch /home/vagrant/.ssh/authorized_keys
          chmod 600 /home/vagrant/.ssh/authorized_keys
          grep -Fqx #{escaped_key} /home/vagrant/.ssh/authorized_keys || printf '%s\\n' #{escaped_key} >> /home/vagrant/.ssh/authorized_keys
          chown vagrant:vagrant /home/vagrant/.ssh/authorized_keys
        SHELL
      end
    end
  end

end
