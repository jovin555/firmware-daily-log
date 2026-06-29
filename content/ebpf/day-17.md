---
title: "Day 17: eBPF for Network Observability: XDP & TC Programs"
date: 2026-06-29
tags: ["til", "ebpf", "xdp", "tc", "networking"]
---

## What I Explored Today

Today I dove into the two primary hook points for eBPF-based network observability: XDP (eXpress Data Path) and TC (Traffic Control). While both allow us to intercept packets, they operate at fundamentally different layers of the kernel networking stack. I built a small observability tool that counts packets by protocol at the XDP layer and then used TC to capture per-flow latency metrics. The combination gives a complete picture from driver-level ingress to the network stack's egress.

## The Core Concept

The key insight is that XDP and TC serve complementary roles. XDP hooks into the network driver's receive path *before* the kernel allocates an `sk_buff` (socket buffer). This means you get raw packet data at the earliest possible moment—ideal for DDoS mitigation, load balancing, and high-speed packet filtering. The trade-off: you cannot access higher-layer kernel structures like sockets or routing tables.

TC programs, on the other hand, attach to the kernel's traffic control layer, which operates after the `sk_buff` is fully constructed. TC hooks are available on both ingress and egress, giving you visibility into packets as they enter and leave the network stack. This is where you want to be for per-flow accounting, QoS marking, or connection tracking.

Why does this matter for observability? If you only instrument at the socket layer (e.g., with `tcpdump`), you miss packets dropped by XDP before they ever reach the stack. Conversely, if you only use XDP, you cannot see retransmissions or TCP state transitions. Running both gives you a complete observability pipeline: XDP for raw packet counts and drops, TC for flow-level metrics and egress monitoring.

## Key Commands / Configuration / Code

### XDP Program: Protocol Counter

This XDP program counts packets by IP protocol and drops all UDP traffic on a specific interface.

```c
// xdp_protocol_counter.c
#include <linux/bpf.h>
#include <linux/if_ether.h>
#include <linux/ip.h>
#include <bpf/bpf_helpers.h>

struct {
    __uint(type, BPF_MAP_TYPE_PERCPU_ARRAY);
    __uint(max_entries, 256);
    __type(key, __u32);
    __type(value, __u64);
} protocol_count SEC(".maps");

SEC("xdp")
int xdp_count_protocol(struct xdp_md *ctx) {
    void *data_end = (void *)(long)ctx->data_end;
    void *data = (void *)(long)ctx->data;
    struct ethhdr *eth = data;

    // Bounds check for Ethernet header
    if (eth + 1 > data_end)
        return XDP_ABORTED;

    // Only process IPv4
    if (bpf_ntohs(eth->h_proto) != ETH_P_IP)
        return XDP_PASS;

    struct iphdr *ip = data + sizeof(struct ethhdr);
    if (ip + 1 > data_end)
        return XDP_ABORTED;

    __u32 key = ip->protocol;
    __u64 *count = bpf_map_lookup_elem(&protocol_count, &key);
    if (count)
        __sync_fetch_and_add(count, 1);

    // Drop UDP (protocol 17) for demonstration
    if (key == IPPROTO_UDP)
        return XDP_DROP;

    return XDP_PASS;
}

char _license[] SEC("license") = "GPL";
```

Compile and attach:
```bash
clang -O2 -target bpf -c xdp_protocol_counter.c -o xdp_protocol_counter.o
ip link set dev eth0 xdp obj xdp_protocol_counter.o sec xdp
```

### TC Program: Per-Flow Latency

This TC egress program records timestamps for TCP SYN packets and calculates RTT when the corresponding SYN-ACK is seen.

```c
// tc_flow_latency.c
#include <linux/bpf.h>
#include <linux/pkt_cls.h>
#include <linux/if_ether.h>
#include <linux/ip.h>
#include <linux/tcp.h>
#include <bpf/bpf_helpers.h>

struct flow_key {
    __u32 saddr;
    __u32 daddr;
    __u16 sport;
    __u16 dport;
};

struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 65536);
    __type(key, struct flow_key);
    __type(value, __u64);
} flow_start SEC(".maps");

SEC("tc")
int tc_measure_latency(struct __sk_buff *skb) {
    void *data_end = (void *)(long)skb->data_end;
    void *data = (void *)(long)skb->data;
    struct ethhdr *eth = data;

    if (eth + 1 > data_end)
        return TC_ACT_OK;

    if (bpf_ntohs(eth->h_proto) != ETH_P_IP)
        return TC_ACT_OK;

    struct iphdr *ip = data + sizeof(struct ethhdr);
    if (ip + 1 > data_end)
        return TC_ACT_OK;

    if (ip->protocol != IPPROTO_TCP)
        return TC_ACT_OK;

    struct tcphdr *tcp = (void *)ip + (ip->ihl * 4);
    if (tcp + 1 > data_end)
        return TC_ACT_OK;

    struct flow_key key = {
        .saddr = ip->saddr,
        .daddr = ip->daddr,
        .sport = bpf_ntohs(tcp->source),
        .dport = bpf_ntohs(tcp->dest),
    };

    __u64 now = bpf_ktime_get_ns();

    if (tcp->syn && !tcp->ack) {
        // SYN: record start time
        bpf_map_update_elem(&flow_start, &key, &now, BPF_ANY);
    } else if (tcp->syn && tcp->ack) {
        // SYN-ACK: lookup start and compute RTT
        __u64 *start = bpf_map_lookup_elem(&flow_start, &key);
        if (start) {
            __u64 rtt_ns = now - *start;
            // Log or aggregate rtt_ns here
            bpf_map_delete_elem(&flow_start, &key);
        }
    }

    return TC_ACT_OK;
}

char _license[] SEC("license") = "GPL";
```

Attach to egress:
```bash
tc qdisc add dev eth0 clsact
tc filter add dev eth0 egress bpf da obj tc_flow_latency.o sec tc
```

### Reading Maps

```bash
# For XDP protocol counts (per-CPU)
bpftool map dump name protocol_count

# For TC flow latency map
bpftool map dump name flow_start
```

## Common Pitfalls & Gotchas

1. **XDP return codes matter for performance.** Returning `XDP_PASS` means the packet continues to the kernel stack—this is fine for observability but adds overhead. If you only want to observe without affecting traffic, use `XDP_PASS` for all packets. Never return `XDP_ABORTED` in production; it signals a driver error and can cause packet loss.

2. **TC programs need a clsact qdisc.** Many engineers forget to add the `clsact` qdisc before attaching TC filters. Without it, `tc filter add` will fail silently or attach to the wrong queueing discipline. Always run `tc qdisc add dev <iface> clsact` first.

3. **Map key alignment in TC vs XDP.** XDP programs see raw packet data, so you must manually handle endianness with `bpf_ntohs()`. TC programs operate on `__sk_buff` where some fields (like `skb->protocol`) are already in host byte order. Mixing the two assumptions will give you wrong keys and silent map lookup failures.

## Try It Yourself

1. **Extend the XDP counter** to also count packets by destination port for TCP traffic. Use a hash map keyed by `(protocol, dport)` and print the top 5 ports every 10 seconds using a user-space program that reads the map via `bpf_map_get_fd_by_id()`.

2. **Add a drop reason to the TC latency program.** Modify the TC egress filter to mark packets with a specific DSCP value if the RTT exceeds 100ms. Use `bpf_skb_change_dsfield()` to set the DSCP field, then verify with `tcpdump -v`.

3. **Build a combined observability dashboard.** Write a Python script using the `bcc` library that loads both the XDP and TC programs, polls their maps every second, and prints a unified view: XDP shows raw packet rates per protocol, TC shows per-flow RTT histograms.

## Next Up

Tomorrow, we shift from network observability to security. I'll explore **eBPF for Security: LSM Hooks & Seccomp Filters**—how to use BPF LSM programs to enforce mandatory access controls and combine them with seccomp for defense-in-depth at the syscall level.
