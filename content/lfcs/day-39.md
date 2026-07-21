---
title: "Day 39: Firewall: iptables, nftables, ufw & firewalld"
date: 2026-07-21
tags: ["til", "lfcs", "firewall", "iptables"]
---

## What I Explored Today

Today I dug into the Linux firewall ecosystem — from the legacy `iptables` to the modern `nftables`, and the two high-level frontends `ufw` and `firewalld`. The LFCS exam expects you to understand the relationship between these tools, not just memorize commands. I spent time tracing packet flow through Netfilter hooks, comparing rule syntax, and testing how each tool interacts with the kernel's firewall subsystem.

## The Core Concept

All Linux firewalls are built on the same kernel infrastructure: **Netfilter**. Netfilter provides five hook points in the network stack (PREROUTING, INPUT, FORWARD, OUTPUT, POSTROUTING). What changes between tools is the *userspace interface*.

`iptables` was the original tool, but its design has fundamental limitations: it processes rules linearly, uses separate tables for different concerns (filter, nat, mangle), and stores state in kernel modules that are hard to extend. `nftables` (the replacement) compiles rules into a single bytecode-like representation, supports sets and maps natively, and can atomically replace rule sets. The kernel module `nf_tables` is far leaner than the legacy `ip_tables` stack.

`ufw` (Uncomplicated Firewall) is a frontend to `iptables` (or `nftables` on newer Ubuntu). It's designed for simplicity — perfect for desktops or single-server setups. `firewalld` is a dynamic firewall manager used by RHEL/CentOS/Fedora. It introduces the concept of *zones* (trusted, public, dmz, etc.) and allows runtime rule changes without flushing existing connections.

The practical takeaway: **learn `nftables` for the future, but know how to read and convert `iptables` rules for legacy systems. Use `ufw` for quick setups, `firewalld` for enterprise environments.**

## Key Commands / Configuration / Code

### iptables — Legacy but everywhere

```bash
# List all rules with line numbers
iptables -L -n -v --line-numbers

# Allow SSH from a specific subnet
iptables -A INPUT -p tcp --dport 22 -s 10.0.0.0/24 -j ACCEPT

# Block all other inbound traffic (policy)
iptables -P INPUT DROP

# Save rules persistently (distro-dependent)
iptables-save > /etc/iptables/rules.v4
```

### nftables — Modern replacement

```bash
# List ruleset
nft list ruleset

# Create a simple table and chain
nft add table inet filter
nft add chain inet filter input { type filter hook input priority 0 \; policy drop \; }

# Allow established connections and SSH
nft add rule inet filter input ct state established,related accept
nft add rule inet filter input tcp dport 22 accept

# Atomic rule replacement from file
cat > /etc/nftables.conf << 'EOF'
table inet filter {
    chain input {
        type filter hook input priority 0; policy drop;
        ct state established,related accept
        iif lo accept
        tcp dport {22, 80, 443} accept
        ip saddr 10.0.0.0/24 accept
    }
}
EOF
nft -f /etc/nftables.conf
```

### ufw — Simple frontend

```bash
# Enable and check status
ufw enable
ufw status verbose

# Default policies
ufw default deny incoming
ufw default allow outgoing

# Allow specific services
ufw allow ssh
ufw allow 80/tcp
ufw allow from 192.168.1.0/24 to any port 3306

# Delete a rule
ufw delete allow 80/tcp

# Enable logging
ufw logging on
```

### firewalld — Zone-based management

```bash
# Check active zone and interfaces
firewall-cmd --get-active-zones

# Add service to public zone (runtime + permanent)
firewall-cmd --zone=public --add-service=http
firewall-cmd --zone=public --add-service=http --permanent

# Rich rules for complex policies
firewall-cmd --zone=public --add-rich-rule='rule family="ipv4" source address="10.0.0.0/24" port port="3306" protocol="tcp" accept'

# Reload to apply permanent changes
firewall-cmd --reload
```

## Common Pitfalls & Gotchas

1. **`iptables` rules are ephemeral by default.** A reboot flushes them unless you explicitly save them. `nftables` rules persist only if you load them from a config file. `firewalld` and `ufw` handle persistence automatically, but `ufw` on older systems still uses `iptables-save` under the hood — check `/etc/ufw/` for the actual rules.

2. **Rule order matters.** `iptables` and `nftables` process rules top-down. A common mistake is adding a `DROP` rule before an `ACCEPT` rule for the same traffic. Always insert permissive rules before restrictive ones. Use `-I` (insert) in `iptables` to place rules at a specific position.

3. **`firewalld` zones can conflict with Docker.** Docker manipulates `iptables` rules directly. If you use `firewalld` with Docker, ensure `firewalld` is running *before* Docker starts, or set `--iptables=false` in Docker daemon config. Otherwise, Docker's rules may be overwritten on `firewalld` reload.

## Try It Yourself

1. **Convert an iptables rule to nftables.** Take this rule: `iptables -A INPUT -p tcp --dport 443 -s 10.0.0.0/8 -j ACCEPT`. Write the equivalent `nftables` rule and add it to a table. Verify with `nft list ruleset`.

2. **Set up a firewalld DMZ zone.** Create a new zone called `dmz` with `firewall-cmd --new-zone=dmz --permanent`. Add HTTP and HTTPS services, then assign a dummy interface (e.g., `eth1`) to it. Reload and verify the zone is active.

3. **Audit your current firewall.** Run `iptables -L -n -v` and `nft list ruleset` (if available). Identify any rules that allow all traffic from `0.0.0.0/0` on sensitive ports (22, 3306, 5432). Tighten them to specific subnets.

## Next Up

Tomorrow we shift from controlling traffic to diagnosing it. **Network Troubleshooting: ss, netstat, tcpdump** — we'll compare socket statistics, trace connections, and capture packets to find what's really happening on the wire. Bring your packet decoder hat.
