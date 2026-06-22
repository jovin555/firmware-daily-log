---
title: "Day 09: Linux Kernel Module: Hello World to Real Device"
date: 2026-06-22
tags: ["til", "embedded-linux", "kernel-module", "lkm"]
---

## What I Explored Today

Today I moved beyond the textbook "Hello World" kernel module and built something that actually interacts with hardware — a minimal GPIO toggling module for an embedded ARM board. The goal was to understand the real scaffolding required to write, compile, load, and debug a Linux Kernel Module (LKM) that talks to a physical device. I used a BeagleBone Black (AM335x) as the target, but the concepts apply directly to any embedded Linux system with GPIOs exposed via sysfs or memory-mapped registers.

## The Core Concept

A kernel module is not a userspace program. It runs in kernel space with ring 0 privileges, has no standard library, and must handle concurrency, memory allocation, and hardware access with extreme care. The "why" behind writing a module instead of a userspace driver is simple: some hardware operations require deterministic timing, interrupt handling, or direct memory-mapped I/O that userspace cannot provide safely.

The real power of an LKM is its ability to be inserted and removed at runtime without rebuilding or rebooting the kernel. This is critical for embedded systems where you might need to support multiple peripherals or update drivers in the field. However, this flexibility comes at a cost: a buggy module can crash the entire system, corrupt filesystems, or cause silent data corruption.

Today's focus was on the minimal viable module that does something observable — toggling a GPIO pin. This requires understanding three things: the module lifecycle (`init` and `exit` functions), kernel memory allocation (`kmalloc` vs `vmalloc`), and hardware register access via `ioremap` or the GPIO subsystem API.

## Key Commands / Configuration / Code

### Minimal Module with GPIO Toggle (using GPIO descriptor API)

```c
// gpio_toggle.c
#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/gpio/consumer.h>
#include <linux/delay.h>
#include <linux/kthread.h>
#include <linux/sched.h>

static struct gpio_desc *led_gpio;
static struct task_struct *toggle_thread;

static int toggle_worker(void *data)
{
    while (!kthread_should_stop()) {
        gpiod_set_value(led_gpio, 1);
        msleep(500);
        gpiod_set_value(led_gpio, 0);
        msleep(500);
    }
    return 0;
}

static int __init gpio_toggle_init(void)
{
    int ret;

    // Request GPIO using descriptor API (device tree based)
    // The label "led0" must match your device tree node's gpio-hog or label
    led_gpio = gpiod_get(NULL, "led0", GPIOD_OUT_LOW);
    if (IS_ERR(led_gpio)) {
        pr_err("Failed to get GPIO led0: %ld\n", PTR_ERR(led_gpio));
        return PTR_ERR(led_gpio);
    }

    // Create a kernel thread to toggle the GPIO
    toggle_thread = kthread_run(toggle_worker, NULL, "gpio_toggle");
    if (IS_ERR(toggle_thread)) {
        pr_err("Failed to create kthread\n");
        gpiod_put(led_gpio);
        return PTR_ERR(toggle_thread);
    }

    pr_info("GPIO toggle module loaded\n");
    return 0;
}

static void __exit gpio_toggle_exit(void)
{
    // Stop the kernel thread
    kthread_stop(toggle_thread);
    // Release the GPIO descriptor
    gpiod_put(led_gpio);
    pr_info("GPIO toggle module unloaded\n");
}

module_init(gpio_toggle_init);
module_exit(gpio_toggle_exit);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("Embedded Engineer");
MODULE_DESCRIPTION("GPIO Toggle Kernel Module");
```

### Makefile for Cross-Compilation

```makefile
# Makefile
obj-m := gpio_toggle.o

# Point to your cross-compiled kernel source tree
KDIR := /path/to/kernel/build/dir

# Cross-compiler prefix (e.g., arm-linux-gnueabihf-)
CROSS_COMPILE := arm-linux-gnueabihf-

all:
	$(MAKE) -C $(KDIR) M=$(PWD) ARCH=arm CROSS_COMPILE=$(CROSS_COMPILE) modules

clean:
	$(MAKE) -C $(KDIR) M=$(PWD) ARCH=arm CROSS_COMPILE=$(CROSS_COMPILE) clean
```

### Building and Loading

```bash
# Build the module
make

# Copy to target (e.g., via scp)
scp gpio_toggle.ko root@192.168.1.100:/tmp/

# On target, load the module
insmod /tmp/gpio_toggle.ko

# Check kernel messages
dmesg | tail -5

# Verify module is loaded
lsmod | grep gpio_toggle

# Unload when done
rmmod gpio_toggle
```

### Checking GPIO State from Userspace

```bash
# If using sysfs GPIO (legacy)
cat /sys/class/gpio/gpio60/value

# If using libgpiod (modern)
gpioinfo | grep -i led
```

## Common Pitfalls & Gotchas

1. **Module version magic mismatch**: The most common error when loading a module is `Invalid module format` or `disagrees about version magic`. This happens when your module was compiled against a different kernel version or configuration than the running kernel. Always compile against the exact kernel source that is running on your target. Use `uname -r` to check the running kernel version.

2. **GPIO descriptor vs legacy GPIO numbers**: The old `gpio_request()` API uses integer GPIO numbers that are board-specific and fragile. The modern descriptor API (`gpiod_get()`) relies on device tree labels, which are portable but require correct device tree bindings. If you get `-EPROBE_DEFER` or `-ENOENT`, your device tree node is missing or mislabeled. Always check `/sys/kernel/debug/gpio` for available GPIOs.

3. **Kernel thread cleanup**: If your module creates a kernel thread, you must ensure it is stopped before the module exits. Failing to call `kthread_stop()` will leave a zombie thread that continues toggling GPIOs even after `rmmod`, potentially causing a kernel panic when the module's code is unmapped. Always check return values from `kthread_stop()` and handle the case where the thread is already stopped.

## Try It Yourself

1. **Modify the toggle rate**: Change the `msleep()` values to 100ms and 1000ms, rebuild, and observe the LED behavior. What happens if you use `mdelay()` instead? (Hint: `mdelay()` is busy-waiting and will lock up your system for 1 second.)

2. **Add a module parameter**: Add a `module_param` for the toggle delay (in ms) so you can set it at load time: `insmod gpio_toggle.ko delay_ms=200`. This is how real drivers expose configuration.

3. **Read a button instead**: Modify the module to read a GPIO input (using `gpiod_get_value()`) and print its state to the kernel log every second. Use `dmesg -w` to watch the output. This is the foundation for interrupt-driven drivers.

## Next Up

Tomorrow, we dive into **Character Device Drivers: cdev, file_operations & ioctl** — the standard interface for exposing kernel functionality to userspace. We'll build a driver that registers a `/dev/mydevice` node, handles `open`, `read`, `write`, and `ioctl` calls, and passes data between kernel and user space safely.
