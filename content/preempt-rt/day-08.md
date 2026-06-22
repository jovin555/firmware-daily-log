---
title: "Day 08: CPU Isolation: isolcpus, nohz_full & rcu_nocbs"
date: 2026-06-22
tags: ["til", "preempt-rt", "isolcpus", "nohz", "rcu"]
---

## What I Explored Today

Today I dug into CPU isolation — the set of kernel boot parameters that carve out dedicated CPUs for real-time tasks. The three main knobs are `isolcpus`, `nohz_full`, and `rcu_nocbs`. Together they form the foundation of deterministic execution on multi-core systems. I tested them on an x86_64 machine with a 6.1 PREEMPT_RT kernel, measuring jitter with cyclictest before and after isolation.

## The Core Concept

The Linux kernel is a busy scheduler. Even when your real-time task is the only runnable thread on a CPU, the kernel still interrupts that CPU for housekeeping: timer ticks, RCU callbacks, load balancing, and workqueues. Each interruption adds latency jitter — sometimes microseconds, sometimes milliseconds.

CPU isolation tells the kernel: *leave these CPUs alone*. The goal is not to make the CPU faster, but to make its execution *predictable*. An isolated CPU should only run tasks explicitly pinned to it, with minimal kernel interference.

Three parameters work together:

- **`isolcpus`** removes CPUs from the general scheduler domain. No regular tasks will be scheduled there unless explicitly pinned via `taskset` or `cpuset`. But it does *not* stop timer ticks or RCU processing.

- **`nohz_full`** (full dynticks) disables the periodic timer tick on isolated CPUs when only one runnable task is present. Without this, every 1ms (or 4ms, depending on `HZ`) a timer interrupt fires, even if nothing needs it. This is the biggest source of jitter.

- **`rcu_nocbs`** offloads RCU callbacks from isolated CPUs to a designated housekeeping CPU. RCU grace-period processing can cause unpredictable delays; offloading moves that overhead away.

The housekeeping CPU (usually CPU 0) handles all the kernel noise. You isolate CPUs 1-N for real-time work, and CPU 0 takes the hit.

## Key Commands / Configuration / Code

### Boot parameters (add to GRUB_CMDLINE_LINUX in /etc/default/grub)

```bash
# Isolate CPUs 1-3, enable full dynticks, offload RCU
# CPU 0 remains as housekeeping
GRUB_CMDLINE_LINUX="isolcpus=1,2,3 nohz_full=1,2,3 rcu_nocbs=1,2,3"
```

After editing, run `update-grub` and reboot.

### Verify isolation is active

```bash
# Check /sys/devices/system/cpu/isolated — should show "1-3"
cat /sys/devices/system/cpu/isolated

# Check nohz_full CPUs
cat /sys/devices/system/cpu/nohz_full

# Check RCU callback offloading
# Look at /proc/rcu_sched — "CB" column shows offloaded CPUs
grep -E "^rcu_sched" /proc/rcu_sched
```

### Pin a real-time task to an isolated CPU

```bash
# Start cyclictest on CPU 1 with SCHED_FIFO priority 95
chrt -f 95 taskset -c 1 cyclictest -l 100000 -m -n -p 95 -i 1000
```

### Measure jitter improvement

Before isolation (on CPU 0, housekeeping):
```bash
cyclictest -l 100000 -m -n -p 95 -i 1000 --smp --affinity=0
# Typical max latency: 50-150 µs
```

After isolation (on CPU 1, isolated):
```bash
cyclictest -l 100000 -m -n -p 95 -i 1000 --smp --affinity=1
# Typical max latency: 5-15 µs
```

### Check RCU callback counts per CPU

```bash
# Watch RCU callbacks queued per CPU
watch -n 1 cat /proc/rcu_sched
# Look for "c" (callbacks) column — isolated CPUs should show 0
```

## Common Pitfalls & Gotchas

### 1. `isolcpus` alone is not enough
Many engineers add `isolcpus` and expect deterministic behavior. Without `nohz_full`, the timer tick still fires every 1-4ms, causing periodic jitter. Without `rcu_nocbs`, RCU callbacks can batch up and cause sudden latency spikes. All three must be used together for real-time work.

### 2. Kernel threads still land on isolated CPUs
`isolcpus` only prevents *user-space* scheduling. Kernel threads (ksoftirqd, kworker, migration) can still run on isolated CPUs unless you explicitly affinitize them. Use `cpuset` cgroups or `/sys/devices/system/cpu/cpu*/hotplug` to fully isolate. A common trick is to offline the isolated CPUs from the kernel's perspective after boot, then online them only for your real-time process.

### 3. Housekeeping CPU overload
Offloading everything to CPU 0 can overwhelm it. If CPU 0 gets stuck handling interrupts, RCU, and timer ticks for 3 other CPUs, it may become a bottleneck. Monitor `/proc/softirqs` and `/proc/interrupts` on CPU 0. For systems with many cores, designate two housekeeping CPUs (e.g., `nohz_full=2-7 rcu_nocbs=2-7` leaving 0-1 for housekeeping).

## Try It Yourself

1. **Baseline measurement**: Boot without any isolation parameters. Run `cyclictest` on CPU 0 and CPU 3 for 100,000 iterations. Record max latency for each. Then add `isolcpus=3 nohz_full=3 rcu_nocbs=3` to your kernel command line, reboot, and repeat the test on CPU 3. Compare the max latency values.

2. **RCU callback inspection**: After booting with isolation, run `watch -n 1 'cat /proc/rcu_sched | grep -E "^rcu_sched"'` while running a real-time workload on an isolated CPU. Verify that the "c" (callbacks) column stays at 0 for isolated CPUs. Then try without `rcu_nocbs` and observe the callback count.

3. **Kernel thread interference**: Boot with only `isolcpus=3` (no `nohz_full` or `rcu_nocbs`). Run `perf top -C 3` while your real-time task runs. Note which kernel functions appear. Then add the other two parameters and repeat — the profile should be much cleaner.

## Next Up

Tomorrow we tackle **IRQ Affinity: Binding Interrupts to Specific CPUs**. Interrupts are another major source of latency jitter. We'll learn how to steer NIC interrupts, timer interrupts, and other IRQs away from your real-time CPUs using `/proc/irq/*/smp_affinity` and the `irqbalance` daemon.
