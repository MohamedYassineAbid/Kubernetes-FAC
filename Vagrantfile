
CLUSTER_NAME      = "Kubernetes Clusterss pfa"
BOX               = "ubuntu/jammy64"

# Network
CONTROL_IP        = "10.0.0.10"
IP_NW             = "10.0.0."
IP_START          = 10
NUM_WORKER_NODES  = 2
SERVICES_IP       = "10.0.0.80"

# Resources
CONTROL_CPU       = 3
CONTROL_MEMORY    = 3072
WORKER_CPU        = 2
WORKER_MEMORY     = 3048
SERVICES_CPU      = 2
SERVICES_MEMORY   = 3072


Vagrant.configure("2") do |config|

  if `uname -m`.strip == "aarch64"
    config.vm.box = BOX + "-arm64"
  else
    config.vm.box = BOX
  end
  config.vm.box_check_update = true

  config.ssh.insert_key = true

  # ── Control Plane 
  config.vm.define "controlplane" do |controlplane|
    controlplane.vm.hostname = "controlplane"
    controlplane.vm.network "private_network", ip: CONTROL_IP
    controlplane.vm.provider "virtualbox" do |vb|
        vb.cpus = CONTROL_CPU
        vb.memory = CONTROL_MEMORY
        if CLUSTER_NAME != ""
          vb.customize ["modifyvm", :id, "--groups", ("/" + CLUSTER_NAME)]
        end
    end
  end

  # ── Worker Nodes 
  (1..NUM_WORKER_NODES).each do |i|
    config.vm.define "node0#{i}" do |node|
      node.vm.hostname = "node0#{i}"
      node.vm.network "private_network", ip: IP_NW + "#{IP_START + i}"
      node.vm.provider "virtualbox" do |vb|
          vb.cpus = WORKER_CPU
          vb.memory = WORKER_MEMORY
          if CLUSTER_NAME != ""
            vb.customize ["modifyvm", :id, "--groups", ("/" + CLUSTER_NAME)]
          end
      end
    end
  end

  # ── Services VM
  config.vm.define "services" do |services|
    services.vm.hostname = "services"
    services.vm.network "private_network", ip: SERVICES_IP
    services.vm.provider "virtualbox" do |vb|
      vb.cpus = SERVICES_CPU
      vb.memory = SERVICES_MEMORY
      if CLUSTER_NAME != ""
        vb.customize ["modifyvm", :id, "--groups", ("/" + CLUSTER_NAME)]
      end
    end
  end

end
