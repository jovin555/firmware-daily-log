---
title: "Day 09: IRQ Affinity: Binding Interrupts to Specific CPUs"
date: 2026-06-22
tags: ["til", "preempt-rt", "irq-affinity", "smp", "cpus"]
---

## What I Explored Today

Today I dug into interrupt affinity — the mechanism that controls which CPU core handles a given hardware interrupt. In a real-time system, this is not optional tuning; it's essential. Without explicit affinity, the kernel's irqbalance daemon or the default SMP balancer will spread interrupts across all cores, causing cache thrashing, unpredictable latency spikes, and priority inversion for your real-time tasks. I spent the morning verifying IRQ assignments on a dual-socket Xeon system running PREEMPT_RT, then manually pinned the NIC and storage controller interrupts to dedicated cores. The latency jitter dropped from ~50 µs to under 8 µs on the isolated CPU.

## The Core Concept

Every hardware interrupt (IRQ) arrives at the CPU's local APIC (Advanced Programmable Interrupt Controller). By default, the kernel distributes IRQs across all available CPUs to balance load. That's fine for a web server, but disastrous for real-time. Here's why:

- **Cache pollution**: When an interrupt handler runs on a core, it evicts the L1/L2 cache lines of whatever real-time task was running there. The task then resumes with cold caches, adding microseconds of latency.
- **Priority inversion**: A high-priority real-time thread can be preempted by an interrupt handler on the same core. Even with PREEMPT_RT, the interrupt handler runs at a higher priority than any user-space task.
- **Non-deterministic scheduling**: If interrupts land on the core running your critical loop, you lose control of timing.

The solution is **IRQ affinity**: pin specific interrupts to specific CPUs, and isolate those CPUs from user-space tasks. This creates a clean separation — interrupt handling on one set of cores, real-time application on another. The real-time core never takes an interrupt, so its cache stays hot and its scheduling stays predictable.

## Key Commands / Configuration / Code

### 1. View current IRQ affinity

```bash
# Show IRQ numbers and their current CPU mask
cat /proc/interrupts

# For a specific IRQ (e.g., 130), show the allowed CPU mask
cat /proc/irq/130/smp_affinity

# Human-readable version (CPU list instead of hex mask)
cat /proc/irq/130/smp_affinity_list
```

### 2. Set IRQ affinity manually

```bash
# Pin IRQ 130 to CPU 2 only (hex mask: 0x04)
echo 04 > /proc/irq/130/smp_affinity

# Or use CPU list format (easier for humans)
echo 2 > /proc/irq/130/smp_affinity_list
```

### 3. Find which device owns an IRQ

```bash
# Look at the Name column in /proc/interrupts, or:
find /sys/kernel/irq/ -name "130" -exec cat {}/actions \;

# More practical: grep for the device driver
cat /proc/interrupts | grep -E "nvme|eth0|i40e"
```

### 4. Persistent configuration via udev (recommended)

Create a udev rule to set affinity on boot:

```bash
# /etc/udev/rules.d/40-irq-affinity.rules
# Pin NVMe controller IRQ to CPU 2
ACTION=="add", SUBSYSTEM=="pci", DRIVER=="nvme", ATTR{irq/smp_affinity}="04"

# Pin i40e NIC IRQs to CPU 3
ACTION=="add", SUBSYSTEM=="pci", DRIVER=="i40e", ATTR{irq/smp_affinity}="08"
```

### 5. Using `irqbalance` with banned CPUs (alternative)

If you must keep irqbalance running, tell it to avoid your real-time cores:

```bash
# /etc/default/irqbalance
IRQBALANCE_BANNED_CPUS=fc  # Mask: CPUs 0-5 allowed, 6-7 banned
IRQBALANCE_ARGS="--oneshot" # Only balance once at boot
```

### 6. Verify isolation with `tuna` (handy tool)

```bash
# Show IRQ affinity and thread CPU affinity in one view
tuna --show_irqs --cpus 0-3

# Move all IRQs away from CPUs 2-3
tuna --irqs '*' --cpus 0-1 --move
```

## Common Pitfalls & Gotchas

**1. The hex mask is reversed from what you expect**  
`smp_affinity` uses a bitmask where bit 0 = CPU 0. But the hex representation is big-endian per byte. To pin to CPU 2 (bit 2), the mask is `04` (not `02`). For CPU 3: `08`. For CPU 7: `80`. Always double-check with `smp_affinity_list` (which shows decimal CPU numbers) before trusting your hex.

**2. MSI-X interrupts are per-queue — you must pin each one**  
Modern NICs and NVMe drives use MSI-X, which creates multiple IRQs (one per hardware queue). Pinning IRQ 130 alone won't help if the device has IRQs 130-137. You must iterate over all of them. Use `ls /sys/kernel/irq/` and look for the device name in the `actions` file of each IRQ.

**3. `irqbalance` will override your manual settings**  
If irqbalance is running (default on most distros), it periodically resets `smp_affinity` for all IRQs. You must either stop irqbalance (`systemctl stop irqbalance`), mask it with `IRQBALANCE_BANNED_CPUS`, or use udev rules that run after irqbalance starts (race condition — better to disable it entirely for RT systems).

## Try It Yourself

1. **Identify your worst interrupt source**: Run `watch -n1 cat /proc/interrupts` while stressing your network or storage. Find the IRQ with the highest count. Check its current affinity with `cat /proc/irq/<N>/smp_affinity_list`. Is it landing on your real-time core?

2. **Pin a device and measure the effect**: Pick a NIC IRQ and pin it to a non-isolated CPU (e.g., CPU 1). Then run a cyclictest on an isolated CPU (e.g., CPU 3). Compare max latency before and after. You should see a measurable improvement.

3. **Write a udev rule for persistence**: Create `/etc/udev/rules.d/40-rt-irq.rules` that pins your storage controller IRQs to CPU 0 and your NIC IRQs to CPU 1. Reboot and verify with `cat /proc/irq/*/smp_affinity_list`.

## Next Up

Tomorrow we tackle **CPU Frequency Scaling: cpufreq & performance Mode**. The kernel's power-saving frequency governors can introduce microsecond-scale jitter by changing clock speeds mid-execution. We'll lock the CPU to a fixed frequency and measure the difference in latency determinism.
