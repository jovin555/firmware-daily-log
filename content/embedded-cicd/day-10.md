---
title: "Day 10: Infrastructure as Code for Build Farms: Ansible & Terraform Basics"
date: 2026-07-10
tags: ["til", "embedded-cicd", "iac", "ansible"]
---

## What I Explored Today

Today I tackled the problem of managing our growing build farm—a mix of bare-metal ARM servers, QEMU VMs for RISC-V cross-compilation, and cloud instances for burst capacity. Manually provisioning each node was a nightmare of SSH sessions, forgotten dependencies, and configuration drift. I dove into Infrastructure as Code (IaC) using Terraform for provisioning and Ansible for configuration management. The goal: a single `terraform apply` and `ansible-playbook` run to spin up a fully reproducible build slave, from OS image to toolchain installation.

## The Core Concept

Embedded build farms are notoriously heterogeneous. You might have:
- A Jenkins master on an x86 VM
- ARM64 slaves for native compilation
- RISC-V QEMU instances for cross-compilation testing
- Windows machines for MCUXpresso or IAR toolchains

Without IaC, each node is a snowflake—unique, undocumented, and terrifying to rebuild. The "why" here is **reproducibility and disaster recovery**. When a build node dies at 2 AM (and it will), you need to replace it in minutes, not days.

Terraform handles the *what*: "I need 3 ARM64 EC2 instances with 16GB RAM and a specific AMI." Ansible handles the *how*: "Install GCC 12.2, CMake 3.28, and mount the NFS share for build artifacts." Separating these concerns means you can swap cloud providers (Terraform) without changing your toolchain setup (Ansible), and vice versa.

## Key Commands / Configuration / Code

### Terraform: Provisioning the Build Slave

```hcl
# main.tf — Terraform configuration for a build farm node
terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

# Data source to find the latest Ubuntu 22.04 ARM64 AMI
data "aws_ami" "ubuntu_arm64" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-arm64-server-*"]
  }

  filter {
    name   = "architecture"
    values = ["arm64"]
  }
}

resource "aws_instance" "build_slave" {
  ami           = data.aws_ami.ubuntu_arm64.id
  instance_type = "c7g.2xlarge"  # Graviton3, 8 vCPU, 16GB RAM
  key_name      = "build-farm-key"

  # Tag for Ansible dynamic inventory
  tags = {
    Name = "build-slave-${count.index}"
    Role = "embedded-build"
  }

  # User data to install Ansible prerequisites
  user_data = <<-EOF
    #!/bin/bash
    apt-get update
    apt-get install -y python3 python3-pip
    pip3 install ansible
  EOF

  # Security group allowing SSH from Jenkins master
  vpc_security_group_ids = [aws_security_group.build_slave_sg.id]

  count = 3  # Spin up 3 identical slaves
}

resource "aws_security_group" "build_slave_sg" {
  name        = "build-slave-sg"
  description = "Allow SSH from Jenkins master only"

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/16"]  # Replace with your VPC CIDR
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
```

### Ansible: Configuring the Toolchain

```yaml
# playbooks/configure-build-slave.yml
---
- name: Configure embedded build slave
  hosts: tag_Role_embedded-build  # Dynamic inventory from Terraform tags
  become: yes
  vars:
    gcc_version: "12.2.0"
    cmake_version: "3.28.1"
    build_workspace: "/opt/build"

  tasks:
    - name: Install system dependencies
      apt:
        name:
          - build-essential
          - git
          - libncurses-dev
          - flex
          - bison
          - qemu-user-static
        state: present
        update_cache: yes

    - name: Create build workspace directory
      file:
        path: "{{ build_workspace }}"
        state: directory
        owner: jenkins
        group: jenkins
        mode: '0755'

    - name: Download and extract ARM GCC toolchain
      unarchive:
        src: "https://developer.arm.com/-/media/Files/downloads/gnu/{{ gcc_version }}/gcc-arm-{{ gcc_version }}-x86_64-arm-none-eabi.tar.xz"
        dest: /opt/toolchains
        remote_src: yes
        creates: "/opt/toolchains/gcc-arm-{{ gcc_version }}"

    - name: Add toolchain to PATH for all users
      copy:
        dest: /etc/profile.d/toolchain.sh
        content: |
          export PATH=$PATH:/opt/toolchains/gcc-arm-{{ gcc_version }}/bin
        mode: '0644'

    - name: Mount NFS share for build artifacts
      mount:
        path: /mnt/build-artifacts
        src: "nfs-server.example.com:/exports/builds"
        fstype: nfs
        opts: "rw,hard,intr,noatime"
        state: mounted
```

### Running the Pipeline

```bash
# Step 1: Provision infrastructure
terraform init
terraform plan -out=tfplan
terraform apply tfplan

# Step 2: Generate Ansible inventory from Terraform state
terraform output -json | jq '...' > inventory.json  # Or use terraform-inventory tool

# Step 3: Configure all nodes
ansible-playbook -i inventory.json playbooks/configure-build-slave.yml
```

## Common Pitfalls & Gotchas

1. **Terraform state file security.** Your `terraform.tfstate` contains plaintext secrets (SSH keys, database passwords). Never commit it to Git. Use a remote backend like S3 with DynamoDB locking: `backend "s3" { bucket = "my-build-farm-tfstate", key = "prod/terraform.tfstate", region = "us-east-1" }`. For embedded teams, consider HashiCorp Cloud Platform or a self-hosted Consul backend.

2. **Ansible idempotency with toolchain downloads.** The `unarchive` module's `creates` parameter is critical. Without it, Ansible re-downloads the 200MB GCC tarball every run. Also, toolchain URLs change—pin versions in `vars` and test the URL before applying to production.

3. **SSH key management across providers.** Terraform creates the instance with a key pair, but Ansible needs the private key. Use `ssh_private_key_file` in your Ansible inventory or `ansible_ssh_private_key_file` in group vars. Never bake keys into AMIs—use SSH agent forwarding or a secrets manager.

## Try It Yourself

1. **Terraform a single build node.** Write a `main.tf` that provisions a t3.micro (x86) or c7g.medium (ARM64) instance with a security group allowing SSH only from your IP. Run `terraform apply`, then SSH in and verify the instance is reachable.

2. **Ansible playbook for toolchain installation.** Create a playbook that installs `gcc-arm-none-eabi` from the Ubuntu repos (simpler than manual download). Use `apt` module with `state: present`. Run it against your Terraform-provisioned node.

3. **Combine Terraform and Ansible.** Use Terraform's `templatefile` function to generate an Ansible inventory file as part of `terraform apply`. Then run `ansible-playbook -i generated_inventory.ini your-playbook.yml` in a single script.

## Next Up

Tomorrow: **Binary Size Regression Tracking Across Builds** — how to catch that 2KB bloat in your firmware before it reaches production, using automated size reports and CI gates. We'll look at `size` output parsing, historical baselines, and breaking the build when `.text` grows too fast.
