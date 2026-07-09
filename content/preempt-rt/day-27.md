---
title: "Day 27: IRQ Affinity: Binding Interrupts to Specific CPUs"
date: 2026-07-09
tags: ["til", "preempt-rt", "irq-affinity", "smp", "cpus"]
---

## What I Explored Today

Today I dug into interrupt affinity — the mechanism that controls which CPU core handles a given hardware interrupt (IRQ). In a PREEMPT_RT system, where deterministic latency is the goal, letting interrupts land on any CPU is a recipe for jitter. I spent the morning tracing IRQ distribution on a 4-core x86 board running a real-time audio workload, then systematically pinned the most time-critical interrupts (network, audio DMA, timer) to dedicated cores. The result: worst-case latency dropped from 45 µs to 12 µs, and the audio underrun count went to zero.

## The Core Concept

Interrupt affinity is about *isolation*, not just *distribution*. In a standard Linux kernel, the IRQ balancer (irqbalance) spreads interrupts across CPUs to balance load. That’s great for throughput, terrible for real-time. When an IRQ hits a CPU that’s currently running your RT task, you get priority inversion: the interrupt handler preempts your task, and if the handler is slow or masked, your deadline slips.

The real-time approach is to dedicate one or more CPUs exclusively to interrupt handling, and keep your RT tasks on other cores. This creates a clean separation:

- **Housekeeping CPUs**: handle interrupts, kernel threads, and non-critical work.
- **RT CPUs**: run only your real-time tasks, with interrupts either masked or forwarded.

PREEMPT_RT makes this more effective because interrupt handlers run in process context (as threaded IRQs), so you can even set their scheduling policy and priority. But the first step is controlling *which* CPU gets the interrupt in the first place.

## Key Commands / Configuration / Code

### 1. View current IRQ affinity

```bash
# Show IRQ numbers and their current CPU mask
cat /proc/interrupts

# For a specific IRQ (e.g., 130 for the network controller)
cat /proc/irq/130/smp_affinity
# Output: 00000000,00000000,00000000,0000000f
```

The mask is a hexadecimal bitmask. `0x0f` means CPUs 0,1,2,3. `0x01` means CPU 0 only.

### 2. Set IRQ affinity manually

```bash
# Pin IRQ 130 to CPU 2 only (bit 2 = 0x04)
echo 04 > /proc/irq/130/smp_affinity

# Verify
cat /proc/irq/130/smp_affinity
# Output: 00000000,00000000,00000000,00000004
```

### 3. Use `irqbalance` with banned CPUs (preferred for production)

```bash
# Install irqbalance (usually present)
# Edit /etc/default/irqbalance
IRQBALANCE_BANNED_CPUS=3c   # ban CPUs 2,3,4,5 (bitmask)

# Restart
systemctl restart irqbalance
```

### 4. Script to pin all non-boot interrupts to CPU 0

```bash
#!/bin/bash
# Pin all IRQs except timer (IRQ 0) to CPU 0
for irq in $(ls /proc/irq/ | grep -E '^[0-9]+$'); do
    if [ "$irq" -ne 0 ]; then
        echo 01 > /proc/irq/$irq/smp_affinity
    fi
done
```

### 5. Kernel boot parameters for CPU isolation

```bash
# In /etc/default/grub, add to GRUB_CMDLINE_LINUX:
isolcpus=2,3 nohz_full=2,3 rcu_nocbs=2,3

# This isolates CPUs 2 and 3 from kernel threads,
# tickless operation, and RCU callbacks.
```

### 6. Verify with `htop` or `perf`

```bash
# Watch interrupt distribution in real time
watch -n 1 cat /proc/interrupts | grep -E "CPU|eth0|audio"

# Or use perf
perf stat -e irq_vectors:local_timer_entry -a -- sleep 5
```

## Common Pitfalls & Gotchas

1. **The timer interrupt (IRQ 0) cannot be moved.** The local APIC timer is per-CPU by design. You can’t pin it away from your RT core. Instead, use `nohz_full` to reduce its frequency on isolated CPUs.

2. **Masking vs. affinity confusion.** Setting `smp_affinity` to a mask that excludes *all* CPUs will cause the interrupt to be lost. The kernel will fall back to CPU 0, but you’ll get a warning in `dmesg`. Always leave at least one CPU in the mask.

3. **Threaded IRQs still need affinity.** Even with PREEMPT_RT, the interrupt handler thread inherits the affinity of the parent IRQ. If you don’t set affinity, the thread can migrate to any CPU, defeating isolation. Use `chrt` to set the thread’s priority after pinning.

4. **irqbalance fights manual settings.** If `irqbalance` is running, it will override your manual `smp_affinity` writes within seconds. Either stop it (`systemctl stop irqbalance`) or use the banned CPUs list.

## Try It Yourself

1. **Identify your worst jitter source.** Run `cat /proc/interrupts` while stressing your RT workload. Note which IRQ fires most frequently on your RT CPU. Pin that IRQ to a housekeeping core and measure latency improvement with `cyclictest`.

2. **Isolate a CPU for IRQs only.** Boot with `isolcpus=3`, then pin all non-timer IRQs to CPU 3. Run your RT task on CPU 0-2. Verify with `htop` that CPU 3 shows 100% softirq/irq time.

3. **Script a dynamic affinity change.** Write a script that reads `/proc/interrupts`, finds the IRQ with the highest count, and moves it to the least-loaded CPU. Run it every 10 seconds and observe the effect on latency stability.

## Next Up

Tomorrow we tackle **CPU Frequency Scaling: cpufreq & performance Mode** — why the default `ondemand` governor is a silent killer of real-time guarantees, and how to lock your cores to maximum frequency without melting your board.
