---
title: "Day 13: SPI Client Drivers: spi_driver & Transfer API"
date: 2026-06-25
tags: ["til", "embedded-linux", "spi", "driver"]
---

## What I Explored Today

Today I dove into writing a real SPI client driver using the Linux kernel's `spi_driver` framework and the `spi_transfer` API. After days of configuring SPI from userspace via `spidev`, I needed to understand how to bind a kernel driver to a specific SPI device and perform reliable, interrupt-driven transfers. The key insight: SPI client drivers live in the kernel's device model, matching against device tree nodes, and use a message-based transfer API that can handle multiple transactions in a single atomic operation.

## The Core Concept

SPI is a synchronous serial bus—every byte sent is simultaneously received. In the kernel, SPI transfers are not simple `read()`/`write()` calls. Instead, you construct `spi_message` objects containing one or more `spi_transfer` segments. Each segment describes a buffer for TX, RX, or both. The controller driver (hardware-specific) then executes the entire message atomically, often using DMA or PIO, while your client driver sleeps on a completion.

Why this design? Because real SPI devices require precise timing: you might need to assert chip select, send a command byte, wait for a response, then deassert—all without other bus traffic interleaving. The message API guarantees that. Additionally, your driver registers with the kernel's device model via `spi_driver`, which calls your `probe()` when a matching device tree node or ACPI entry is found. This decouples hardware discovery from driver logic.

## Key Commands / Configuration / Code

### Device Tree Binding

First, ensure your SPI device node is present. For a fictional temperature sensor on SPI bus 0, chip select 1:

```dts
&spi0 {
    status = "okay";
    temp_sensor: temp@1 {
        compatible = "mycorp,tmp123";
        reg = <1>;          // chip select 0-based
        spi-max-frequency = <1000000>;
        /* optional: SPI mode flags */
        spi-cpha;
        spi-cpol;
    };
};
```

### Minimal SPI Client Driver

Here's a complete driver skeleton that reads a 2-byte temperature register every time the device is opened:

```c
#include <linux/module.h>
#include <linux/spi/spi.h>
#include <linux/fs.h>
#include <linux/cdev.h>
#include <linux/slab.h>

#define DRV_NAME "tmp123"

struct tmp123_dev {
    struct spi_device *spi;
    struct cdev cdev;
    dev_t dev_num;
};

/* Synchronous SPI transfer: send 1 byte, receive 2 bytes */
static int tmp123_read_temp(struct tmp123_dev *dev, u16 *temp)
{
    u8 tx_buf = 0x00;          // command: read temp register
    u8 rx_buf[2];
    struct spi_transfer tr = {
        .tx_buf = &tx_buf,
        .rx_buf = rx_buf,
        .len = 3,              // one byte TX, two bytes RX
        .cs_change = 0,        // keep CS asserted for entire message
    };
    struct spi_message msg;

    spi_message_init(&msg);
    spi_message_add_tail(&tr, &msg);

    /* This blocks until transfer completes or timeout */
    if (spi_sync(dev->spi, &msg) < 0)
        return -EIO;

    *temp = (rx_buf[0] << 8) | rx_buf[1];
    return 0;
}

static int tmp123_probe(struct spi_device *spi)
{
    struct tmp123_dev *dev;
    int ret;

    dev = devm_kzalloc(&spi->dev, sizeof(*dev), GFP_KERNEL);
    if (!dev)
        return -ENOMEM;

    dev->spi = spi;
    spi_set_drvdata(spi, dev);

    /* Allocate char device region (simplified) */
    alloc_chrdev_region(&dev->dev_num, 0, 1, DRV_NAME);
    cdev_init(&dev->cdev, &tmp123_fops);
    cdev_add(&dev->cdev, dev->dev_num, 1);

    dev_info(&spi->dev, "TMP123 probed at CS%d, max freq %d Hz\n",
             spi->chip_select, spi->max_speed_hz);
    return 0;
}

static void tmp123_remove(struct spi_device *spi)
{
    struct tmp123_dev *dev = spi_get_drvdata(spi);
    cdev_del(&dev->cdev);
    unregister_chrdev_region(dev->dev_num, 1);
}

static const struct of_device_id tmp123_of_match[] = {
    { .compatible = "mycorp,tmp123" },
    { }
};
MODULE_DEVICE_TABLE(of, tmp123_of_match);

static struct spi_driver tmp123_driver = {
    .driver = {
        .name = DRV_NAME,
        .of_match_table = tmp123_of_match,
    },
    .probe = tmp123_probe,
    .remove = tmp123_remove,
};

module_spi_driver(tmp123_driver);
MODULE_LICENSE("GPL");
```

### Building and Testing

Compile as a kernel module (out-of-tree):

```bash
make -C /lib/modules/$(uname -r)/build M=$PWD modules
```

Insert and verify:

```bash
sudo insmod tmp123.ko
# Check dmesg for probe message
dmesg | tail -5
# Verify device created under /sys/bus/spi/devices/spi0.1/
ls /sys/bus/spi/devices/spi0.1/
```

## Common Pitfalls & Gotchas

1. **Mixing TX and RX buffer lengths**: If you set `tr.len = 3` but only provide a 1-byte `tx_buf`, the kernel will DMA-read past your buffer. Always ensure `tx_buf` and `rx_buf` are at least `len` bytes, or set one to NULL if half-duplex. The controller will clock out zeros for NULL TX.

2. **Forgetting `cs_change` semantics**: By default, chip select deasserts after each `spi_transfer` in a message. If your device needs CS held across multiple transfers (e.g., command + response), set `cs_change = 0` on all but the last transfer, or set it to 1 only on the final one. Misunderstanding this causes devices to reset mid-command.

3. **Sleeping in atomic context**: `spi_sync()` is a blocking call that uses a completion. Never call it from interrupt context, spinlock-held sections, or `timer` callbacks. Use `spi_async()` instead, which returns immediately and invokes a callback on completion.

## Try It Yourself

1. **Modify the driver to use `spi_write_then_read()`**: Replace the manual `spi_message` construction with the helper function `spi_write_then_read()`. Compare code complexity and verify the same functionality.

2. **Add SPI mode configuration from device tree**: Extend the driver to read `spi-cpha` and `spi-cpol` properties and log the resulting mode. Then force a mismatch (e.g., set mode in driver that contradicts DT) and observe the kernel warning.

3. **Implement asynchronous transfers**: Rewrite the temperature read to use `spi_async()` with a completion callback. Use `wait_for_completion_timeout()` in your read function and handle the timeout case gracefully.

## Next Up

Tomorrow I'll tackle **GPIO & Interrupt Handling in Kernel Drivers** — wiring up a GPIO interrupt to wake your SPI driver, using `devm_request_irq()` and threaded IRQ handlers to avoid blocking the interrupt line while waiting for SPI transfers.
