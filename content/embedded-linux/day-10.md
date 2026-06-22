---
title: "Day 10: Character Device Drivers: cdev, file_operations & ioctl"
date: 2026-06-22
tags: ["til", "embedded-linux", "char-driver", "ioctl"]
---

## What I Explored Today

Today I finally got my hands dirty with character device drivers — the most fundamental type of driver in Linux. I implemented a minimal driver that registers a `cdev` structure, hooks into `file_operations`, and added an `ioctl` interface for custom control. The goal was to understand the lifecycle: from `alloc_chrdev_region()` to `cdev_add()`, and then how user space interacts via `open`, `read`, `write`, and `ioctl`. I also learned why `ioctl` is both powerful and dangerous, and how to use the `_IOR/_IOW` macros correctly.

## The Core Concept

Character devices are the simplest abstraction in the Linux driver model: they handle data as a stream of bytes, one character at a time (think serial ports, GPIO, or sensors). The kernel provides three core pieces:

1. **`dev_t` and `cdev`** — the device number (major/minor) and the kernel object that represents your device.
2. **`file_operations`** — a struct of function pointers that maps system calls (like `read()`) to your driver’s handlers.
3. **`ioctl`** — the escape hatch for operations that don’t fit the read/write model (e.g., setting baud rate, configuring a sensor mode).

The *why* is critical: user space cannot touch hardware directly (MMIO, interrupts, privileged registers). The driver is the gatekeeper. `ioctl` gives you a way to pass arbitrary commands and data between user and kernel space, but it’s also the most common source of bugs — wrong direction flags, missing permission checks, or buffer overflows.

## Key Commands / Configuration / Code

Here’s a minimal but complete character driver skeleton. I’ll walk through the registration, operations, and ioctl.

```c
#include <linux/module.h>
#include <linux/fs.h>
#include <linux/cdev.h>
#include <linux/uaccess.h>
#include <linux/ioctl.h>

#define DEVICE_NAME "my_char_dev"
#define CLASS_NAME  "my_class"

static dev_t dev_num;
static struct cdev my_cdev;
static struct class *my_class;
static struct device *my_device;

/* ioctl command definition */
#define MY_IOCTL_MAGIC 'k'
#define MY_IOCTL_GET_VALUE _IOR(MY_IOCTL_MAGIC, 0, int)
#define MY_IOCTL_SET_VALUE _IOW(MY_IOCTL_MAGIC, 1, int)

static int my_value = 42;  // internal state

static int my_open(struct inode *inode, struct file *filp) {
    pr_info("Device opened\n");
    return 0;
}

static int my_release(struct inode *inode, struct file *filp) {
    pr_info("Device closed\n");
    return 0;
}

static ssize_t my_read(struct file *filp, char __user *buf,
                       size_t count, loff_t *f_pos) {
    char msg[] = "Hello from kernel!\n";
    size_t len = strlen(msg);
    if (count < len) return -EINVAL;
    if (copy_to_user(buf, msg, len)) return -EFAULT;
    return len;
}

static ssize_t my_write(struct file *filp, const char __user *buf,
                        size_t count, loff_t *f_pos) {
    pr_info("Received %zu bytes from user\n", count);
    return count;  // pretend we consumed it
}

static long my_ioctl(struct file *filp, unsigned int cmd, unsigned long arg) {
    int tmp;
    switch (cmd) {
        case MY_IOCTL_GET_VALUE:
            if (copy_to_user((int __user *)arg, &my_value, sizeof(my_value)))
                return -EFAULT;
            break;
        case MY_IOCTL_SET_VALUE:
            if (copy_from_user(&tmp, (int __user *)arg, sizeof(tmp)))
                return -EFAULT;
            my_value = tmp;
            pr_info("Value set to %d\n", my_value);
            break;
        default:
            return -ENOTTY;  // "not a typewriter" — standard ioctl error
    }
    return 0;
}

static struct file_operations fops = {
    .owner   = THIS_MODULE,
    .open    = my_open,
    .release = my_release,
    .read    = my_read,
    .write   = my_write,
    .unlocked_ioctl = my_ioctl,  // modern kernels use unlocked_ioctl
};

static int __init my_init(void) {
    // 1. Allocate device number (dynamic)
    if (alloc_chrdev_region(&dev_num, 0, 1, DEVICE_NAME) < 0) {
        pr_err("Failed to allocate dev num\n");
        return -1;
    }
    pr_info("Major: %d, Minor: %d\n", MAJOR(dev_num), MINOR(dev_num));

    // 2. Initialize and add cdev
    cdev_init(&my_cdev, &fops);
    my_cdev.owner = THIS_MODULE;
    if (cdev_add(&my_cdev, dev_num, 1) < 0) {
        pr_err("cdev_add failed\n");
        unregister_chrdev_region(dev_num, 1);
        return -1;
    }

    // 3. Create device class and device (for /dev node)
    my_class = class_create(THIS_MODULE, CLASS_NAME);
    if (IS_ERR(my_class)) {
        cdev_del(&my_cdev);
        unregister_chrdev_region(dev_num, 1);
        return PTR_ERR(my_class);
    }
    my_device = device_create(my_class, NULL, dev_num, NULL, DEVICE_NAME);
    if (IS_ERR(my_device)) {
        class_destroy(my_class);
        cdev_del(&my_cdev);
        unregister_chrdev_region(dev_num, 1);
        return PTR_ERR(my_device);
    }
    return 0;
}

static void __exit my_exit(void) {
    device_destroy(my_class, dev_num);
    class_destroy(my_class);
    cdev_del(&my_cdev);
    unregister_chrdev_region(dev_num, 1);
    pr_info("Module removed\n");
}

module_init(my_init);
module_exit(my_exit);
MODULE_LICENSE("GPL");
```

Build with a standard kernel Makefile. Load with `insmod`, then test:

```bash
# Check device node created by udev
ls -l /dev/my_char_dev

# Read from it
cat /dev/my_char_dev

# Test ioctl from user space (write a small C program)
int fd = open("/dev/my_char_dev", O_RDWR);
int val;
ioctl(fd, MY_IOCTL_GET_VALUE, &val);   // val == 42
val = 100;
ioctl(fd, MY_IOCTL_SET_VALUE, &val);   // sets internal state
```

## Common Pitfalls & Gotchas

1. **Using `ioctl` instead of `unlocked_ioctl`** — In kernels 2.6.36+, the `ioctl` field in `file_operations` is gone. You must use `.unlocked_ioctl` (which takes `unsigned long arg` instead of `unsigned long`). If you use the old name, the kernel won’t call your handler and user space gets `ENOTTY`.

2. **Forgetting `copy_from_user` / `copy_to_user`** — Never dereference user-space pointers directly. The kernel can’t trust them; they might point to swapped-out pages or invalid memory. Always use the `copy_*_user` functions, and check their return value.

3. **Not checking `ioctl` command direction** — The `_IOR` and `_IOW` macros encode the data direction in the command number. Your driver should verify the direction matches. If user space sends a write command but you try to read, you’ll corrupt memory. Use `_IOC_DIR(cmd)` to validate.

## Try It Yourself

1. **Add a `llseek` operation** — Implement `.llseek` in `file_operations` to support `lseek()` from user space. Use `fixed_size_llseek()` or write your own that tracks `f_pos`.

2. **Implement a multi-instance driver** — Modify the driver to support multiple minor numbers (e.g., 4 devices). Use `container_of()` in `open()` to associate each `file` with a per-device structure.

3. **Add permission checking to `ioctl`** — Use `capable(CAP_SYS_ADMIN)` to restrict `MY_IOCTL_SET_VALUE` to root only. Return `-EPERM` if the caller lacks privilege.

## Next Up

Tomorrow, I’ll move from raw character drivers to **Platform Drivers & Device Tree Binding**. We’ll see how the kernel matches drivers to hardware using `struct platform_driver` and `of_match_table`, and how to read device tree properties like `reg`, `interrupts`, and `compatible`. This is the standard way to write drivers for memory-mapped peripherals on ARM/embedded systems.
