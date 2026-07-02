---
title: "Day 20: Sysfs & Debugfs: Kernel-Userspace Interface"
date: 2026-07-02
tags: ["til", "embedded-linux", "sysfs", "debugfs"]
---

## What I Explored Today

Today I dug into two of the most essential kernel-userspace interfaces in embedded Linux: sysfs and debugfs. While both expose kernel data to userspace, they serve very different purposes. Sysfs is the stable, structured interface for device and driver information — think GPIOs, LEDs, regulators, and power management. Debugfs is the wild west: a no-rules, no-stability-guarantee filesystem for dumping anything a kernel developer wants to expose during development. I spent the day tracing GPIO toggles through sysfs and poking at driver internals via debugfs on a BeagleBone Black.

## The Core Concept

The kernel needs a way to talk to userspace without breaking userspace programs every time a driver changes. Sysfs provides that contract: it exports a well-defined, documented hierarchy under `/sys` that userspace can rely on. Every device gets a directory under `/sys/devices/`, every driver gets a `uevent` file, and every GPIO pin gets a `direction` and `value` attribute. The interface is stable across kernel versions — Linus Torvalds has famously yelled at developers who break sysfs ABI.

Debugfs is the opposite. Mounted at `/sys/kernel/debug/`, it exists purely for debugging and development. There are no ABI guarantees. A driver can export raw register dumps, interrupt counters, or internal state structures without worrying about userspace compatibility. The rule is simple: if you're writing a driver and need to expose something for testing, use debugfs. If you're designing a production interface, use sysfs.

The practical distinction: sysfs is for control and configuration. Debugfs is for observation and debugging. Mixing them up will get your kernel patches rejected.

## Key Commands / Configuration / Code

### Mounting and Exploring

```bash
# Sysfs is usually mounted automatically, but you can verify:
mount | grep sysfs
# Output: sysfs on /sys type sysfs (rw,nosuid,nodev,noexec,relatime)

# Debugfs often needs manual mounting:
mount -t debugfs none /sys/kernel/debug
# Or add to /etc/fstab: debugfs /sys/kernel/debug debugfs defaults 0 0
```

### GPIO Control via Sysfs (Legacy but still common)

```bash
# Export GPIO 60 (P9_12 on BeagleBone)
echo 60 > /sys/class/gpio/export

# Set direction and value
echo out > /sys/class/gpio/gpio60/direction
echo 1 > /sys/class/gpio/gpio60/value

# Read back
cat /sys/class/gpio/gpio60/value

# Unexport when done
echo 60 > /sys/class/gpio/unexport
```

### Debugfs: Reading Driver Internals

```bash
# List available debugfs entries
ls /sys/kernel/debug/

# Read a driver's register dump (example: i2c)
cat /sys/kernel/debug/i2c/0-0048/registers

# Watch interrupt counts in real-time
watch -n 1 cat /sys/kernel/debug/irq/irqs
```

### Creating a Sysfs Attribute in a Kernel Driver

```c
// Example: simple sysfs attribute for a custom driver
static ssize_t my_value_show(struct device *dev,
                             struct device_attribute *attr, char *buf)
{
    struct my_driver_data *data = dev_get_drvdata(dev);
    return scnprintf(buf, PAGE_SIZE, "%d\n", data->current_value);
}

static ssize_t my_value_store(struct device *dev,
                              struct device_attribute *attr,
                              const char *buf, size_t count)
{
    struct my_driver_data *data = dev_get_drvdata(dev);
    int ret = kstrtoint(buf, 10, &data->current_value);
    if (ret < 0)
        return ret;
    return count;
}

static DEVICE_ATTR_RW(my_value);
```

### Creating a Debugfs Entry

```c
// In driver probe:
struct dentry *debug_dir;
debug_dir = debugfs_create_dir("my_driver", NULL);
debugfs_create_u32("reg_value", 0644, debug_dir, &data->register_value);
debugfs_create_bool("debug_enable", 0644, debug_dir, &data->debug_flag);
```

## Common Pitfalls & Gotchas

1. **Sysfs attribute naming collisions**: Sysfs is flat within a device directory. If two drivers export an attribute named `power`, they conflict. Always check existing attributes before adding new ones. The kernel's `Documentation/ABI/` directory documents every stable attribute.

2. **Debugfs entries persist after driver removal**: If your driver creates debugfs entries in probe but doesn't clean them up in remove, you'll get stale entries pointing to freed memory. Always use `debugfs_remove_recursive()` in your remove callback. A crash is the best-case outcome; silent data corruption is worse.

3. **PAGE_SIZE buffer assumption**: When writing sysfs show/store functions, the kernel provides a `PAGE_SIZE` buffer (usually 4096 bytes). If you write more than that, you'll truncate. Always use `scnprintf()` instead of `sprintf()` to guarantee null-termination within the buffer.

## Try It Yourself

1. **GPIO blink via sysfs**: Export a GPIO on your board, set it as output, and toggle it in a shell loop (`while true; do echo 1 > value; sleep 0.5; echo 0 > value; sleep 0.5; done`). Verify with an LED or oscilloscope.

2. **Explore debugfs**: Mount debugfs and read `/sys/kernel/debug/clk/clk_summary` (if available) to see clock tree frequencies. Compare with what `cat /proc/cpuinfo` reports.

3. **Write a minimal sysfs attribute**: Create a kernel module that exports a single integer attribute via sysfs. Write a userspace program that reads and writes to it. Verify the value persists across writes.

## Next Up

Tomorrow: **GDB Cross-Debug: JTAG, gdbserver & Remote Debug** — how to debug a crashing embedded target from your host machine using GDB's remote protocol, JTAG adapters, and gdbserver. We'll cover setting up a cross-debugging session, attaching to a running process, and debugging kernel panics via JTAG.
