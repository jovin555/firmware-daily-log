---
title: "Day 37: Network Interfaces: ip, ifconfig & Link Management"
date: 2026-07-19
tags: ["til", "lfcs", "networking", "interfaces"]
---

## What I Explored Today

Today I dug into Linux network interface management, specifically the `ip` command from the `iproute2` suite and the legacy `ifconfig` from `net-tools`. While `ifconfig` still works on most systems, the modern `ip` command is the standard tool for production environments, especially on minimal containers or systems without net-tools installed. I focused on bringing interfaces up/down, viewing link state, setting IP addresses, and understanding the difference between temporary and persistent configuration.

## The Core Concept

Network interfaces are the kernel's abstraction for any hardware or virtual device that can send and receive packets. Every interface has a **link state** (UP/DOWN), a **MAC address** (layer 2), and optionally one or more **IP addresses** (layer 3). The `ip` command operates at both layers: `ip link` manages the physical/virtual link state and MAC, while `ip addr` manages IP addressing.

Why does this matter? Because misconfigured interfaces are the #1 cause of "network is down" in production. You need to know how to check link state (is the cable plugged in?), how to assign IPs without rebooting, and how to make changes survive a reboot. The `ip` command is also scriptable and machine-parseable, making it essential for automation.

## Key Commands / Configuration / Code

### Viewing Interface State

```bash
# Show all interfaces with link state, MAC, and stats
ip link show

# Show only active (UP) interfaces
ip link show up

# Show IP addresses assigned to all interfaces
ip addr show

# Show only a specific interface (e.g., eth0)
ip addr show eth0

# Legacy equivalent (still works, but avoid in scripts)
ifconfig -a
ifconfig eth0
```

### Bringing Interfaces Up/Down

```bash
# Bring interface down (disconnects, removes routes)
sudo ip link set eth0 down

# Bring interface up
sudo ip link set eth0 up

# Legacy equivalents
sudo ifconfig eth0 down
sudo ifconfig eth0 up
```

**Important:** `ip link set eth0 down` removes all IP addresses and routes associated with that interface. It does not just "disable" it—it tears down the network stack for that device.

### Assigning IP Addresses (Temporary)

```bash
# Add an IPv4 address (temporary, lost on reboot)
sudo ip addr add 192.168.1.100/24 dev eth0

# Add a second IP (IP aliasing)
sudo ip addr add 192.168.1.101/24 dev eth0

# Remove an IP
sudo ip addr del 192.168.1.100/24 dev eth0

# Legacy equivalent
sudo ifconfig eth0 192.168.1.100 netmask 255.255.255.0
```

### Persistent Configuration (per distribution)

On **Debian/Ubuntu** (`/etc/network/interfaces`):

```bash
auto eth0
iface eth0 inet static
    address 192.168.1.100/24
    gateway 192.168.1.1
    dns-nameservers 8.8.8.8
```

On **RHEL/CentOS/Fedora** (`/etc/sysconfig/network-scripts/ifcfg-eth0`):

```bash
DEVICE=eth0
BOOTPROTO=static
ONBOOT=yes
IPADDR=192.168.1.100
NETMASK=255.255.255.0
GATEWAY=192.168.1.1
DNS1=8.8.8.8
```

On **systemd-networkd** (`/etc/systemd/network/10-eth0.network`):

```bash
[Match]
Name=eth0

[Network]
Address=192.168.1.100/24
Gateway=192.168.1.1
DNS=8.8.8.8
```

### Checking Link State Programmatically

```bash
# Get carrier state (cable plugged in?)
cat /sys/class/net/eth0/carrier
# Returns 1 (up) or 0 (down)

# Get link speed and duplex
ethtool eth0 | grep -E "Speed|Duplex"
```

## Common Pitfalls & Gotchas

1. **`ifconfig` shows only active interfaces by default** — `ifconfig -a` shows all, including DOWN interfaces. Many engineers forget the `-a` flag and miss a disabled interface that should be up.

2. **`ip addr add` does not persist across reboots** — This is the most common mistake. You add an IP, test it, reboot, and the interface comes up with no IP. Always update the distribution-specific config file or use `nmcli` (NetworkManager) for persistence.

3. **Duplicate IPs cause silent failures** — If you assign the same IP to two interfaces on the same subnet, the kernel will accept it, but only one will respond to ARP requests. Always check with `arping` or `ip neigh` before assigning.

4. **Interface naming changes** — Modern systems use predictable names like `enp0s3` or `ens33` instead of `eth0`. Scripts hardcoded to `eth0` will fail. Use `ip link` to discover the actual names.

## Try It Yourself

1. **Identify all interfaces** — Run `ip link show` and `ip addr show`. Note the MAC address, link state, and any IPs assigned. Compare with `ifconfig -a` output.

2. **Temporarily break and fix an interface** — On a test VM or container, bring an interface down with `sudo ip link set eth0 down`, verify with `ip link show`, then bring it back up. Check that the IP address is restored (or re-add it if it was lost).

3. **Add a persistent IP** — Edit your distribution's network config file (e.g., `/etc/network/interfaces` on Debian) to add a static IP. Reboot or restart networking (`sudo systemctl restart networking`) and verify the IP persists.

## Next Up

Tomorrow we move up the stack: **DNS resolution, SSH configuration, and port forwarding**. We'll cover `/etc/resolv.conf`, `systemd-resolved`, SSH tunnels, and how to forward ports through firewalls. See you then.
