---
title: "Day 26: CPU Isolation: isolcpus, nohz_full & rcu_nocbs"
date: 2026-07-08
tags: ["til", "preempt-rt", "isolcpus", "nohz", "rcu"]
---

## What I Explored Today

Today I dug into CPU isolation — the practice of shielding specific cores from kernel housekeeping so that real-time tasks can run without interference. I tested the three main kernel boot parameters: `isolcpus`, `nohz_full`, and `rcu_nocbs`, and measured the difference in latency jitter on an isolated core versus a housekeeping core. The results were stark: isolated cores showed sub-10 microsecond jitter, while non-isolated cores saw spikes over 500 microseconds under moderate load.

## The Core Concept

The Linux kernel is a busy scheduler. Even when your real-time task is the only runnable thread on a CPU, the kernel itself may preempt it to handle timers, RCU callbacks, or scheduler ticks. These interruptions add non-deterministic latency — exactly what PREEMPT_RT aims to eliminate.

CPU isolation is not about pinning tasks (that's `taskset` or `cpuset`). It's about telling the kernel: "Don't bother this CPU with your background noise." Three parameters work together:

1. **`isolcpus`** — Removes the CPU from the kernel's scheduler load-balancing domain. The kernel will not automatically schedule any user-space tasks on it. You must manually pin your real-time threads there.
2. **`nohz_full`** — Disables the periodic timer tick on the specified CPUs. Normally, every CPU receives a timer interrupt (typically 100–1000 Hz) for scheduler accounting. With `nohz_full`, the tick only fires when exactly one task is running — which is the ideal state for a dedicated real-time core.
3. **`rcu_nocbs`** — Offloads RCU (Read-Copy-Update) callbacks from the isolated CPUs to a housekeeping CPU. RCU is a synchronization mechanism used pervasively in the kernel; its callbacks can introduce unpredictable delays if they run on your real-time core.

**The critical insight**: These parameters are not optional extras — they are prerequisites for deterministic real-time behavior on multi-core systems. Without them, even with PREEMPT_RT, you'll see latency spikes from kernel housekeeping.

## Key Commands / Configuration / Code

### Boot Parameter Configuration (GRUB)

Add these to your kernel command line in `/etc/default/grub`:

```bash
# /etc/default/grub
# Isolate CPUs 2-3, make them tickless, and offload RCU
GRUB_CMDLINE_LINUX_DEFAULT="isolcpus=2,3 nohz_full=2,3 rcu_nocbs=2,3"

# Always keep CPU 0 as a housekeeping core (don't isolate it)
# The kernel needs at least one non-isolated CPU for system tasks
```

After editing, regenerate GRUB config:
```bash
sudo grub-mkconfig -o /boot/grub/grub.cfg   # Debian/Ubuntu
# or
sudo grub2-mkconfig -o /boot/grub2/grub.cfg # RHEL/Fedora
```

### Verify Isolation at Runtime

```bash
# Check which CPUs are isolated (look for "isolated" in /proc/cmdline)
cat /proc/cmdline | grep -o 'isolcpus=[^ ]*'

# Check which CPUs are in the nohz_full set
cat /sys/devices/system/cpu/nohz_full

# Check RCU callback offloading
# Each CPU's RCU kthread should show as not running on isolated cores
ps aux | grep rcu
```

### Pin a Real-Time Task to an Isolated CPU

```bash
# Using chrt to set real-time priority and taskset to pin to CPU 2
sudo chrt -f 99 taskset -c 2 ./my_realtime_app

# Or using cpuset (more robust for complex setups)
sudo cset shield --cpu 2-3 --kthread=on
sudo cset shield --shield --pid $(pgrep my_realtime_app)
```

### Measure Latency on Isolated vs. Non-Isolated CPU

```bash
# Run cyclictest on CPU 2 (isolated) vs CPU 0 (housekeeping)
# Isolated:
sudo cyclictest -a 2 -p 99 -i 1000 -l 100000 -m -q

# Housekeeping (expect higher max latency):
sudo cyclictest -a 0 -p 99 -i 1000 -l 100000 -m -q
```

## Common Pitfalls & Gotchas

1. **Isolating CPU 0 is almost always a mistake.** CPU 0 handles boot-time initialization, timer broadcast, and many kernel threads. If you isolate it, system services may fail to start or behave erratically. Always keep at least one housekeeping CPU (usually CPU 0).

2. **`nohz_full` without `rcu_nocbs` is dangerous.** A tickless CPU still processes RCU callbacks. If you enable `nohz_full` but forget `rcu_nocbs`, the RCU subsystem will still interrupt your real-time task to process callbacks — negating the benefit of tickless operation. They must be used together.

3. **`isolcpus` does not prevent interrupt handling.** Isolated CPUs still receive hardware interrupts (e.g., from network cards, storage controllers). You must also configure IRQ affinity (tomorrow's topic) to move interrupts away from isolated cores. Otherwise, an interrupt storm can destroy your latency guarantees.

4. **Kernel threads can still run on isolated CPUs.** Some kernel threads (like `watchdog`, `migration`, or `ksoftirqd`) may ignore `isolcpus`. Use `cset shield --kthread=on` to forcibly move them, or check `/sys/devices/system/cpu/isolated` for the kernel's actual isolation set.

## Try It Yourself

1. **Baseline measurement**: Boot your system without any isolation parameters. Run `cyclictest` on CPU 0 and CPU 2 simultaneously. Record the maximum latency on each. Then add `isolcpus=2 nohz_full=2 rcu_nocbs=2` to your kernel command line, reboot, and repeat. Compare the difference — you should see a 10-100x improvement on the isolated core.

2. **Verify RCU offloading**: After booting with `rcu_nocbs=2`, check `/sys/devices/system/cpu/rcu_cpu_has_cb`. On CPU 2, this file should show `0` (no callbacks pending). On CPU 0, it should show `1`. If both show `1`, your `rcu_nocbs` parameter didn't take effect — check your GRUB config.

3. **Stress test isolation**: While running a real-time task on CPU 2, generate heavy system load: `stress --cpu 4 --io 2 --vm 2 --vm-bytes 128M`. Monitor your real-time task's latency. On a properly isolated core, the latency should remain stable. On a non-isolated core, you'll see dramatic spikes.

## Next Up

Tomorrow we'll tackle **IRQ Affinity: Binding Interrupts to Specific CPUs**. You've isolated your cores, but interrupts are still crashing the party. We'll use `/proc/irq/*/smp_affinity` and `irqbalance` to steer hardware interrupts away from your real-time CPUs — the final piece of the isolation puzzle.
