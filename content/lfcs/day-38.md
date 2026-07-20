---
title: "Day 38: DNS, SSH & Port Forwarding"
date: 2026-07-20
tags: ["til", "lfcs", "dns", "ssh", "security"]
---

## What I Explored Today

Today I dug into the practical intersection of DNS resolution, SSH tunneling, and port forwarding — three networking pillars that every Linux engineer must wield fluently. While each concept is straightforward in isolation, their combination is where real power emerges: forwarding local ports through SSH to bypass firewalls, resolving internal hostnames across VPNs, and securely exposing services without opening new firewall holes. I focused on the exact commands and configurations that solve real-world access problems, not textbook theory.

## The Core Concept

DNS and SSH serve fundamentally different roles, but they complement each other in distributed systems. DNS maps human-readable names to IP addresses; SSH provides encrypted transport and authentication. Port forwarding is the glue that lets you route traffic across network boundaries.

The key insight: **SSH port forwarding creates encrypted tunnels that bypass network restrictions, but without proper DNS resolution, those tunnels are useless.** When you forward port 3306 on your laptop to a remote MySQL server, your local client still needs to resolve the database hostname — either via `/etc/hosts`, a local DNS resolver, or by forwarding DNS queries through the same SSH tunnel.

Modern SSH supports three forwarding modes:
- **Local forwarding** (`-L`): Listen on your machine, forward to a remote destination
- **Remote forwarding** (`-R`): Listen on the remote machine, forward back to your local network
- **Dynamic forwarding** (`-D`): Create a SOCKS proxy that tunnels arbitrary traffic

The real engineering challenge is deciding *which* mode to use and *how* to handle DNS alongside it.

## Key Commands / Configuration / Code

### 1. Basic Local Port Forwarding

```bash
# Forward local port 8080 to internal web server at 10.0.1.50:80
# through bastion host jump.example.com
ssh -L 8080:10.0.1.50:80 user@jump.example.com

# Multiple forwards in one command
ssh -L 8080:10.0.1.50:80 -L 3306:db.internal:3306 user@jump.example.com
```

### 2. Dynamic SOCKS Proxy with DNS Tunneling

```bash
# Create SOCKS5 proxy on local port 1080
# All DNS queries also go through the tunnel
ssh -D 1080 -N user@bastion.example.com

# Configure applications to use SOCKS5 proxy at 127.0.0.1:1080
# For curl:
curl --socks5-hostname 127.0.0.1:1080 http://internal-service.corp
```

The `--socks5-hostname` flag is critical — it sends the hostname to the proxy, which resolves it on the remote side. Without it, your local DNS resolver would try to resolve `internal-service.corp` and fail.

### 3. SSH Config for Persistent Tunnels

```ini
# ~/.ssh/config
Host bastion
    HostName bastion.example.com
    User engineer
    IdentityFile ~/.ssh/id_ed25519
    LocalForward 8080 10.0.1.50:80
    LocalForward 3306 db.internal:3306
    DynamicForward 1080
    ExitOnForwardFailure yes
    ServerAliveInterval 60
```

Then simply `ssh bastion` to establish all forwards.

### 4. Testing DNS Resolution Through Tunnel

```bash
# Verify DNS works through the tunnel
# First, start the SOCKS proxy
ssh -D 1080 -N bastion

# In another terminal, use dig through the proxy
dig @8.8.8.8 internal-service.corp \
    -p 53 \
    +tcp \
    -b 127.0.0.1 \
    +proxy=socks5://127.0.0.1:1080

# Or use proxychains for any command
# Install: apt install proxychains4
# Configure /etc/proxychains4.conf with "socks5 127.0.0.1 1080"
proxychains4 curl http://internal-service.corp
```

### 5. Remote Port Forwarding (Reverse Tunnel)

```bash
# On a machine behind NAT, expose its SSH to the internet
# Forward remote port 2222 to local port 22
ssh -R 2222:localhost:22 user@public-server.com

# Now from public-server.com:
ssh -p 2222 localhost
# This connects back to the NAT'd machine
```

## Common Pitfalls & Gotchas

**1. DNS Leakage in SOCKS Proxies**
When using `-D`, many applications still perform DNS resolution locally before sending traffic to the proxy. This leaks internal hostnames to your local DNS resolver (or ISP). Always use `--socks5-hostname` with curl, or configure your browser to use "SOCKS5 proxy" (not "SOCKS5 proxy with DNS") — the latter still resolves locally in some implementations. The `proxychains4` tool handles this correctly by intercepting DNS calls.

**2. GatewayPorts for Remote Forwarding**
By default, remote port forwarding (`-R`) binds only to `127.0.0.1` on the remote server. To make it accessible to other hosts, you need `GatewayPorts yes` in the remote server's `/etc/ssh/sshd_config`, or use `-R 0.0.0.0:2222:localhost:22`. Without this, you'll waste hours wondering why connections from other machines fail.

**3. SSH Timeouts Killing Tunnels**
Long-lived tunnels drop silently when idle. Always set `ServerAliveInterval 60` and `ServerAliveCountMax 3` in your SSH config. For production tunnels, use `autossh` which automatically restarts failed connections:
```bash
autossh -M 0 -o "ServerAliveInterval 60" -o "ServerAliveCountMax 3" \
    -L 3306:db.internal:3306 bastion
```

## Try It Yourself

1. **Set up a SOCKS proxy through a remote server** and verify DNS resolution works by accessing an internal-only web service. Use `curl --socks5-hostname` and compare it with `curl --socks5` to see the DNS leak difference.

2. **Create a reverse SSH tunnel** from a machine behind NAT to a public server. Connect back through the tunnel and verify you can SSH into the NAT'd machine. Then add `GatewayPorts` to make it accessible to a third machine.

3. **Write an SSH config file** that establishes three local forwards and one dynamic forward simultaneously. Test with `ssh -N bastion` and verify each forward with `netstat -tlnp | grep ssh`.

## Next Up

Tomorrow we lock down the network: **Firewall: iptables, nftables, ufw & firewalld** — the tools that decide who gets through your tunnels in the first place.
