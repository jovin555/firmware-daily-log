---
title: "Day 40: Network Troubleshooting: ss, netstat, tcpdump"
date: 2026-07-22
tags: ["til", "lfcs", "troubleshooting", "networking"]
---

## What I Explored Today

Today I dove into the three essential tools every Linux engineer reaches for when the network misbehaves: `ss`, `netstat`, and `tcpdump`. While `netstat` has been the go-to for decades, `ss` is now the modern replacement, and `tcpdump` remains the gold standard for packet-level inspection. I focused on real-world scenarios — identifying port conflicts, spotting connection leaks, and capturing traffic to diagnose latency or dropped packets.

## The Core Concept

Network troubleshooting is fundamentally about answering three questions: *What is listening?*, *What is connected?*, and *What is on the wire?* The first two are about socket state — which processes own which ports, and how many connections are in each TCP state (ESTABLISHED, TIME_WAIT, CLOSE_WAIT). The third is about packet capture — seeing the actual bytes flowing between hosts.

`ss` and `netstat` both read from `/proc/net/tcp`, `/proc/net/udp`, and related kernel interfaces. `ss` is faster because it uses netlink sockets instead of parsing procfs, and it exposes more detailed socket information (like TCP congestion algorithm, memory usage, and cgroup). `tcpdump` uses libpcap to put the network interface into promiscuous mode and capture raw frames, which it can filter with BPF (Berkeley Packet Filter) expressions.

The key insight: always start with `ss` to check local state, then use `tcpdump` to confirm what’s actually leaving or arriving at the interface. Never guess — capture.

## Key Commands / Configuration / Code

### Socket Statistics with `ss`

```bash
# Show all listening TCP sockets with process info
ss -tlnp
# -t: TCP only
# -l: listening only
# -n: numeric (no DNS)
# -p: show process (requires root for non-owned sockets)

# Show all established connections, human-readable
ss -tuna | head -20
# -u: UDP as well
# -a: all (listening + established)

# Filter by state: show connections stuck in CLOSE_WAIT
ss -t state close-wait

# Show socket memory usage (useful for tuning)
ss -t -m
# -m: memory details (rcvbuf, wmem, etc.)

# Show all connections to a specific port
ss -tun dst :443
```

### Legacy `netstat` (still useful on older systems)

```bash
# Show listening programs with numeric ports
netstat -tulpn
# -t: TCP, -u: UDP, -l: listening, -p: program, -n: numeric

# Show routing table (alternative to ip route)
netstat -rn

# Show interface statistics (packet drops, errors)
netstat -i
```

### Packet Capture with `tcpdump`

```bash
# Capture traffic on eth0, no DNS resolution, write to file
tcpdump -i eth0 -nn -w /tmp/capture.pcap

# Read a capture file with timestamps
tcpdump -r /tmp/capture.pcap -tttt

# Capture HTTP traffic (port 80) with hex dump
tcpdump -i any -nn -X port 80

# Capture only SYN packets (new connection attempts)
tcpdump -i eth0 'tcp[tcpflags] & tcp-syn != 0 and tcp[tcpflags] & tcp-ack == 0'

# Capture traffic between two hosts
tcpdump -i eth0 -nn host 10.0.0.1 and host 10.0.0.2

# Capture with a BPF filter for port range
tcpdump -i eth0 'tcp portrange 8000-8010'
```

### Practical Debugging Workflow

```bash
# Step 1: Is anything listening on port 8080?
ss -tlnp | grep 8080

# Step 2: Are there connections in weird states?
ss -t state fin-wait-2

# Step 3: Capture 10 packets to see what's happening
tcpdump -i any -c 10 -nn port 8080

# Step 4: Check if kernel is dropping packets
netstat -s | grep -i drop
# or
nstat -az | grep -i drop
```

## Common Pitfalls & Gotchas

1. **`netstat` is not installed by default on modern distros.** On RHEL 9, Ubuntu 22.04+, and most container images, `netstat` requires the `net-tools` package. Always use `ss` first — it’s part of `iproute2`, which is always present. I’ve seen engineers waste time installing net-tools when `ss` was already there.

2. **`tcpdump` drops packets if the buffer overflows.** By default, the kernel’s capture buffer is small (often 2MB). On busy interfaces, you’ll see “packet loss” in the capture summary. Always add `-B 4096` (4MB buffer) for production captures. Also, never write to NFS — write to a local disk or tmpfs.

3. **`ss -p` requires root for processes owned by other users.** If you run `ss -tlnp` as a non-root user, you’ll see `users:(("",pid=0,fd=0))` for sockets owned by other users. Use `sudo ss -tlnp` to see the actual process names and PIDs.

4. **TCP state machine confusion.** A socket in `TIME_WAIT` is normal and harmless (it’s the 2MSL wait). But a socket in `CLOSE_WAIT` means the remote side closed but your application hasn’t called `close()` — that’s a bug. A growing number of `FIN_WAIT2` sockets often indicates a misconfigured keepalive or a firewall that’s sending RST packets.

## Try It Yourself

1. **Find a port conflict.** Start two processes listening on the same port (e.g., `nc -l 9999 &` then `nc -l 9999`). Use `ss -tlnp` to see which process got the bind. Then use `tcpdump -i lo -nn port 9999` to see what happens when you connect.

2. **Detect a connection leak.** Write a short script that opens 100 TCP connections to a local service (like `curl localhost:80` in a loop). Use `watch -n 1 'ss -t state close-wait'` to see if connections accumulate. Then use `ss -t -m` to check socket memory usage.

3. **Capture and analyze a three-way handshake.** Run `tcpdump -i lo -nn -c 3 'tcp port 80'` in one terminal. In another, run `curl http://localhost:80` (ensure something is listening). Examine the SYN, SYN-ACK, ACK sequence. Then add `-v` to see TCP options like MSS and window scaling.

## Next Up

Tomorrow, we shift from troubleshooting to serving: **HTTP Servers: Apache & nginx**. We’ll cover virtual hosts, SSL termination, and performance tuning — the tools you need to deploy and debug web traffic at scale.
