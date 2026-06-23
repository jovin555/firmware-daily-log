---
title: "Day 11: Platform Drivers & Device Tree Binding"
date: 2026-06-23
tags: ["til", "embedded-linux", "platform-driver", "dt-binding"]
---

## What I Explored Today

Today I dug into the marriage between platform drivers and Device Tree (DT) bindings. Platform drivers are the workhorses of embedded Linux—they handle devices that aren't discoverable via enumerable buses like PCI or USB. But without proper DT binding, your driver is just code floating in space. I walked through the full lifecycle: writing a DT node, matching it with a `of_match_table`, and handling resource extraction from the tree. The key takeaway? The DT binding isn't just documentation—it's the contract between firmware and driver.

## The Core Concept

Why do we need platform drivers at all? On embedded SoCs, most peripherals (UARTs, SPI controllers, GPIO banks) are memory-mapped and hardwired. There's no "plug and play" discovery. The kernel needs to know: what address does this device live at? Which interrupt line does it use? What clock rate does it need? Before DT, this was hardcoded in board files—a maintenance nightmare.

Platform drivers solve this by decoupling the driver logic from the hardware description. The driver declares "I can handle these compatible strings," and the kernel matches them against DT nodes. The DT provides the configuration; the driver provides the behavior. This separation means you can run the same kernel binary on different boards by just swapping the DT blob.

The `platform_driver` structure is your entry point. You register it, and the kernel's driver model calls your `probe()` when a matching DT node is found. Inside `probe()`, you use `devm_platform_ioremap_resource()` to get your memory region, `platform_get_irq()` for interrupts, and `device_property_read_*` APIs for custom properties. The "devm_" prefix means managed resources—the kernel cleans up automatically on driver removal or error.

## Key Commands / Configuration / Code

Here's a minimal but complete platform driver with DT binding. I'll use a fictional "acme,led-controller" device.

**DT node (in your board.dts):**
```dts
/ {
    leds {
        compatible = "acme,led-controller";
        reg = <0x0 0x4a100000 0x0 0x1000>;
        interrupts = <0 42 4>;  // SPI, IRQ 42, active high
        acme,blink-rate-ms = <500>;
        acme,max-brightness = <255>;
    };
};
```

**Driver skeleton (acme-led.c):**
```c
#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/of.h>
#include <linux/of_device.h>
#include <linux/interrupt.h>

static const struct of_device_id acme_led_of_match[] = {
    { .compatible = "acme,led-controller" },
    { /* sentinel */ }
};
MODULE_DEVICE_TABLE(of, acme_led_of_match);

static irqreturn_t acme_led_isr(int irq, void *dev_id)
{
    // Handle interrupt—clear status, toggle LED, etc.
    return IRQ_HANDLED;
}

static int acme_led_probe(struct platform_device *pdev)
{
    struct device *dev = &pdev->dev;
    struct resource *res;
    void __iomem *base;
    int irq, ret;
    u32 blink_rate;

    // Get memory region from DT "reg" property
    base = devm_platform_ioremap_resource(pdev, 0);
    if (IS_ERR(base))
        return PTR_ERR(base);

    // Get interrupt from DT "interrupts" property
    irq = platform_get_irq(pdev, 0);
    if (irq < 0)
        return irq;

    // Read custom property from DT
    ret = device_property_read_u32(dev, "acme,blink-rate-ms", &blink_rate);
    if (ret)
        blink_rate = 1000;  // default if not specified

    // Request IRQ
    ret = devm_request_irq(dev, irq, acme_led_isr, 0,
                           dev_name(dev), dev);
    if (ret)
        return ret;

    dev_info(dev, "probed at %pR, irq %d, blink %u ms\n",
             res, irq, blink_rate);
    return 0;
}

static int acme_led_remove(struct platform_device *pdev)
{
    dev_info(&pdev->dev, "removed\n");
    return 0;
}

static struct platform_driver acme_led_driver = {
    .probe  = acme_led_probe,
    .remove = acme_led_remove,
    .driver = {
        .name = "acme-led",
        .of_match_table = acme_led_of_match,
    },
};
module_platform_driver(acme_led_driver);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("Your Name");
MODULE_DESCRIPTION("ACME LED Controller Platform Driver");
```

**Build and test:**
```bash
# Build as module
make -C /path/to/kernel M=$PWD modules

# Load and verify
insmod acme-led.ko
cat /sys/bus/platform/drivers/acme-led/...  # check bindings
dmesg | tail  # should show probe message
```

## Common Pitfalls & Gotchas

1. **Mismatched compatible strings** — The most frequent bug. Your DT says `"acme,led-controller"` but your driver's `of_match_table` has `"acme,led-ctrl"`. The kernel silently skips your driver. Always double-check with `dtc -I dtb -O dts` to dump the compiled DT and grep for your string.

2. **Forgetting MODULE_DEVICE_TABLE** — Without this macro, the module doesn't export its device ID table. The kernel can't match your driver to DT nodes when loaded as a module. You'll see "driver not found" in `dmesg`. Add it—it's not optional.

3. **Resource index confusion** — `devm_platform_ioremap_resource(pdev, 0)` maps the first `reg` entry. If your DT has multiple `reg` ranges (e.g., `reg = <0x4a100000 0x1000 0x4a200000 0x2000>`), index 0 gets the first, index 1 the second. Same for `platform_get_irq(pdev, 0)`. Off-by-one here causes silent memory corruption or NULL pointer dereferences.

## Try It Yourself

1. **Add a second DT property** — Extend the example above with an `acme,led-color` string property. In `probe()`, read it with `device_property_read_string()` and print it. Test by changing the DT and recompiling.

2. **Implement a sysfs interface** — Add a `struct attribute_group` to expose the blink rate as a writable sysfs file. Use `device_create_file()` in `probe()`. Write to it from userspace and verify the driver reads the new value.

3. **Debug a binding mismatch** — Intentionally break the compatible string in your DT (e.g., `"acme,led-broken"`). Rebuild the DT, boot, and check `dmesg | grep acme`. Then fix it and confirm the driver probes. This trains your eye for the most common failure mode.

## Next Up

Tomorrow: **I2C Client Drivers: i2c_driver & Adapter API** — We'll move from memory-mapped platform devices to the I2C bus. You'll learn how to write an `i2c_driver`, handle `i2c_client` instantiation from DT, and use the adapter API for register-level communication. Bring your logic analyzer—we're going bit-banging.
