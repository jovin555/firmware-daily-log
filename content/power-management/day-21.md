---
title: "Day 21: suspend/resume: System Sleep States in Linux"
date: 2026-07-03
tags: ["til", "power-management", "suspend", "resume", "sleep-states"]
---

## What I Explored Today

Today I dug into the Linux kernel's system sleep state machine — specifically how `suspend-to-RAM` (S3), `suspend-to-idle` (S0ix), and `hibernate` (S4) actually work under the hood. I traced the entire path from `echo mem > /sys/power/state` through the PM core, platform firmware, and device driver callbacks. The key insight? The kernel doesn't just "pause" — it orchestrates a coordinated freeze of userspace, a device-by-device suspend chain, and a platform-specific firmware handoff. Understanding this chain is critical for debugging wake-up failures, battery drain during suspend, and resume latency issues on embedded Linux systems.

## The Core Concept

System sleep states exist because turning a device completely off (S5) is too slow for interactive use, but leaving everything running (S0) wastes power. The kernel abstracts this through four primary states exposed in `/sys/power/state`:

- **freeze** (suspend-to-idle): Freezes userspace, puts CPUs into idle, but leaves devices active. Lowest latency (~100ms resume), highest power in sleep.
- **standby** (S1): Power-on suspend. CPU stops, caches flushed, but RAM retains state. Rarely used on modern ARM/x86.
- **mem** (S3): Suspend-to-RAM. RAM is self-refreshed, all other devices powered off. Typical laptop/embedded sleep.
- **disk** (S4): Hibernate. RAM contents written to swap, system fully powers off. Zero power consumption, but slowest resume.

The critical engineering distinction: **S3 requires platform firmware (BIOS/ACPI/UEFI) cooperation**, while `freeze` is purely kernel-managed. On embedded systems without ACPI (most ARM boards), `mem` often maps to a vendor-specific firmware call, and `freeze` is the only portable option.

The suspend/resume flow follows a strict order:
1. Userspace is frozen (all tasks stopped)
2. Sysfs/device suspend notifications sent
3. Non-boot CPUs offlined
4. Devices suspended in reverse probe order (leaf drivers first)
5. System core (timers, interrupts) suspended
6. Platform firmware invoked (ACPI `\_S3` or vendor hook)
7. On resume, everything reverses

## Key Commands / Configuration / Code

### Check available sleep states
```bash
# Shows supported states: freeze, mem, disk (subset may appear)
cat /sys/power/state

# Typical output on x86 laptop:
# freeze mem disk
# On embedded ARM (no ACPI):
# freeze
```

### Trigger a suspend
```bash
# Suspend to RAM (S3)
echo mem > /sys/power/state

# Suspend to idle (freeze)
echo freeze > /sys/power/state

# Hibernate (requires swap partition/file)
echo disk > /sys/power/state
```

### Debug wake-up sources
```bash
# Show what can wake the system (before suspend)
cat /sys/power/wakeup_count
cat /proc/acpi/wakeup

# Enable/disable wakeup for a device
echo enabled > /sys/devices/.../power/wakeup
```

### Kernel config for sleep debugging
```bash
# Enable verbose suspend/resume logging
echo 1 > /sys/power/pm_print_times
# Or set kernel boot parameter: pm_print_times=1

# Measure device suspend/resume latency
echo 1 > /sys/power/pm_debug_messages
# Then check dmesg for per-device timing:
dmesg | grep "PM: suspend"
```

### Device driver suspend/resume callbacks (example)
```c
// In a platform driver's struct dev_pm_ops
static int my_device_suspend(struct device *dev)
{
    struct my_priv *priv = dev_get_drvdata(dev);
    
    // Save hardware state before power is removed
    priv->saved_reg = readl(priv->base + REG_CTRL);
    // Gate clock and assert reset
    clk_disable_unprepare(priv->clk);
    
    dev_dbg(dev, "suspended\n");
    return 0;
}

static int my_device_resume(struct device *dev)
{
    struct my_priv *priv = dev_get_drvdata(dev);
    
    // Re-enable clock, de-assert reset
    clk_prepare_enable(priv->clk);
    // Restore hardware state
    writel(priv->saved_reg, priv->base + REG_CTRL);
    
    dev_dbg(dev, "resumed\n");
    return 0;
}

// Assign to PM operations
static const struct dev_pm_ops my_pm_ops = {
    .suspend = my_device_suspend,
    .resume  = my_device_resume,
    .freeze  = my_device_suspend,   // Same for hibernate freeze
    .thaw    = my_device_resume,    // Same for hibernate thaw
    .poweroff = my_device_suspend,  // For S5 shutdown
    .restore  = my_device_resume,   // For restore from hibernate
};
```

## Common Pitfalls & Gotchas

**1. "echo mem" fails silently on non-ACPI systems**
On ARM boards without firmware support, `mem` may return immediately or hang. Always check `dmesg | tail` after a suspend attempt. If you see `PM: suspend entry (deep)` followed by immediate resume, the platform likely lacks S3 support. Use `freeze` instead — it's universally supported and often sufficient for embedded use cases.

**2. Resume fails because a device IRQ fires before driver re-initializes**
If your device shares an interrupt line and the IRQ handler accesses hardware that isn't restored yet, you'll get a kernel panic or lockup. Fix: use `dev_pm_set_wake_irq()` to mark wake IRQs, and ensure your resume callback re-enables interrupts only after full state restoration. Always test with `CONFIG_PM_DEBUG=y` and `pm_test` modes.

**3. Hibernate (disk) silently corrupts filesystems on embedded systems**
Many embedded boards lack a swap partition large enough for full RAM contents. Hibernate writes an atomic image, but if the storage driver doesn't support `noflush` or the rootfs is on the same device, you can corrupt the filesystem. Always verify swap size >= RAM, and use `resume=` kernel parameter pointing to the correct swap device.

## Try It Yourself

1. **Profile your system's sleep states**: Run `cat /sys/power/state` on your target board. If `mem` is listed, try `echo mem > /sys/power/state` and measure resume time with `time` or a GPIO toggled in a resume notifier. Compare to `echo freeze`.

2. **Debug a device that prevents suspend**: Use `cat /proc/acpi/wakeup` (x86) or check `sys/devices/*/power/control`. Find a device with `disabled` wakeup capability, enable it, then attempt suspend. Watch `dmesg` for "device failed to suspend" errors.

3. **Write a minimal PM callback**: Add a `struct dev_pm_ops` to a simple platform driver (e.g., a GPIO controller). Implement `suspend`/`resume` that saves/restores one register. Insert the driver, trigger `echo freeze > /sys/power/state`, and verify your callbacks fire via `dmesg`.

## Next Up

Tomorrow we go deeper into the device level: **Runtime PM: dev_pm_ops & rpm_suspend/resume**. We'll explore how individual devices can enter low-power states while the rest of the system stays awake — the foundation for aggressive power management in always-on embedded systems.
