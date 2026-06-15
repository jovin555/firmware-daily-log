---
title: "Day 03: suspend/resume: System Sleep States in Linux"
date: 2026-06-15
tags: ["til", "power-management", "suspend", "resume", "sleep-states"]
---

## What I Explored Today

Today I dug into the Linux kernel's system sleep state machine — the `suspend-to-idle`, `standby`, `suspend-to-RAM`, and `hibernate` paths. I traced through the PM core code, tested each state on an i.MX8M Plus board, and validated wake sources using RTC and GPIO. The goal was to understand not just *which* states exist, but *how* the kernel transitions between them and what an embedded engineer must verify to ensure reliable suspend/resume.

## The Core Concept

System sleep states are about trading power for wake latency. The Linux kernel exposes four primary states via `/sys/power/state`:

- **freeze** (suspend-to-idle, S0ix on x86): firmware stays awake, CPUs idle, devices runtime-suspended. Wake latency: microseconds.
- **standby** (Power-On Suspend, S1 on x86): some peripherals powered off, CPU clock gated. Wake latency: milliseconds.
- **mem** (Suspend-to-RAM, S3 on x86): RAM in self-refresh, most SoC blocks powered off. Wake latency: tens of milliseconds.
- **disk** (Hibernate, S4 on x86): RAM image written to swap, system fully off. Wake latency: seconds.

The critical insight: **suspend/resume is a driver-by-driver contract**. The PM core calls each device's `suspend` callback in reverse probe order, then `suspend_noirq` with interrupts disabled. Resume runs the mirror path. If *any* driver fails to save/restore its hardware context, the system may hang, corrupt data, or fail to wake.

On embedded systems, the SoC-specific suspend code (e.g., `imx8_pm_suspend` in `arch/arm64/mach-imx`) handles the deepest states — powering off the GIC, L2 cache, and DDR controller while keeping a wake-up controller alive. The board designer's job is to ensure all wake-capable devices (RTC, GPIO, Ethernet PHY) are correctly wired and their drivers implement `suspend`/`resume` properly.

## Key Commands / Configuration / Code

### 1. Check available sleep states
```bash
# Read supported states from sysfs
cat /sys/power/state
# Typical output: freeze mem disk
# On some embedded boards: freeze standby mem disk
```

### 2. Enter a sleep state
```bash
# Suspend-to-RAM (deepest on most SoCs)
echo mem > /sys/power/state

# Suspend-to-idle (lowest latency)
echo freeze > /sys/power/state

# Hibernate (requires swap partition)
echo disk > /sys/power/state
```

### 3. Configure wake-up sources (RTC example)
```bash
# Set RTC alarm 10 seconds from now, then suspend
rtcwake -m mem -s 10

# -m mem: enter suspend-to-RAM
# -s 10: alarm in 10 seconds
# Alternative: -m freeze for suspend-to-idle
```

### 4. Kernel driver suspend/resume skeleton (minimal example)
```c
// From a platform driver's struct dev_pm_ops
static int mydev_suspend(struct device *dev)
{
    struct mydev_data *data = dev_get_drvdata(dev);

    // Save hardware context before power is removed
    data->saved_reg = readl(data->reg_base + CTRL_REG);
    // Disable interrupts to prevent spurious wake
    writel(0, data->reg_base + INT_ENABLE);
    return 0;
}

static int mydev_resume(struct device *dev)
{
    struct mydev_data *data = dev_get_drvdata(dev);

    // Restore hardware context after power returns
    writel(data->saved_reg, data->reg_base + CTRL_REG);
    // Re-enable interrupts
    writel(data->int_mask, data->reg_base + INT_ENABLE);
    return 0;
}

static const struct dev_pm_ops mydev_pm_ops = {
    .suspend = mydev_suspend,
    .resume  = mydev_resume,
};
```

### 5. Debugging suspend/resume with ftrace
```bash
# Trace PM core callbacks during suspend
echo 1 > /sys/kernel/debug/tracing/events/power/suspend_resume/enable
echo 1 > /sys/kernel/debug/tracing/tracing_on
echo mem > /sys/power/state
cat /sys/kernel/debug/tracing/trace | grep "suspend\|resume"
```

## Common Pitfalls & Gotchas

### 1. **Missing wake-up interrupt configuration**
The most common failure: you suspend, but the system never wakes. The culprit is almost always a device whose IRQ is not marked as a wake-up source. Check with:
```bash
cat /proc/acpi/wakeup   # x86
cat /sys/kernel/debug/wakeup_sources   # generic
```
Ensure the wake-capable device has `enabled` in its `power/wakeup` sysfs node:
```bash
echo enabled > /sys/devices/.../power/wakeup
```

### 2. **Driver suspend callback returns -EBUSY**
If a driver refuses to suspend (e.g., because a file is open or a DMA transfer is in flight), the entire suspend sequence aborts. Always check `dmesg` for "PM: Device ... failed to suspend: error -16". The fix is either to close the resource or implement `suspend_late` to force-stop DMA.

### 3. **Resume hangs on noirq stage**
The `suspend_noirq` and `resume_noirq` phases run with interrupts disabled. If a driver's `resume_noirq` tries to spin on a register that never returns to a valid state, the system deadlocks. Always add a timeout or poll with a maximum retry count in noirq callbacks.

## Try It Yourself

1. **Measure wake latency** — On your target board, run `rtcwake -m freeze -s 5` and time the return to shell with `time`. Repeat for `mem`. Compare the two latencies. What accounts for the difference?

2. **Find a broken driver** — Suspend your system, then check `dmesg | grep -i "PM\|suspend\|resume"`. Identify any driver that prints a warning or error. Read that driver's source to see if it saves/restores all hardware registers.

3. **Add a wake-up source** — Connect a GPIO button to a SoC pin that supports wake. Write a minimal kernel module that registers the GPIO IRQ as a wake-up source (`device_init_wakeup(dev, true)`). Suspend with `mem` and press the button to wake.

## Next Up

Tomorrow: **Runtime PM: dev_pm_ops & rpm_suspend/resume** — we'll move from system-wide sleep to per-device dynamic power management, covering the `pm_runtime_get/put` API, autosuspend, and how to avoid the "runtime PM ping-pong" that kills battery life.
