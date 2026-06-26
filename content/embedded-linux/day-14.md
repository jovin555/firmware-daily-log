---
title: "Day 14: GPIO & Interrupt Handling in Kernel Drivers"
date: 2026-06-26
tags: ["til", "embedded-linux", "gpio", "interrupts"]
---

## What I Explored Today

Today I wired up a physical button to a GPIO line on an i.MX8M Mini board and wrote a kernel driver that handles the interrupt—no polling, no busy loops, just clean edge-triggered IRQ handling. I’ve done GPIO toggling from userspace via sysfs and libgpiod, but the real control lives in the kernel. I needed to debounce in software, manage IRQ flags correctly, and avoid sleeping in atomic context. Here’s what I learned.

## The Core Concept

GPIO interrupts in the kernel are not just about detecting a pin change—they’re about responding to hardware events with minimal latency and zero wasted CPU cycles. Userspace polling burns power and adds jitter. A kernel interrupt handler runs in a special context (atomic, no scheduling) and can either handle the event immediately or defer the heavy lifting to a threaded handler or workqueue.

The key design decision: what runs in the hard IRQ handler (top half) vs. the threaded handler (bottom half). The top half must be fast and non-blocking—typically just reading the GPIO status and clearing the interrupt flag. The bottom half can sleep, acquire mutexes, and perform I/O. For a simple button press, the bottom half might schedule a debounce timer or update a shared state.

## Key Commands / Configuration / Code

### Device Tree Binding

First, the GPIO key is described in the device tree. This is how the kernel knows which pin to use and what interrupt type to expect.

```dts
/ {
    gpio-keys {
        compatible = "gpio-keys";
        pinctrl-names = "default";
        pinctrl-0 = <&pinctrl_key>;

        user-button {
            label = "user-button";
            gpios = <&gpio1 12 GPIO_ACTIVE_LOW>;
            linux,code = <KEY_ENTER>;
            gpio-key,wakeup;
            interrupt-parent = <&gpio1>;
            interrupts = <12 IRQ_TYPE_EDGE_FALLING>;
        };
    };
};

&iomuxc {
    pinctrl_key: keygrp {
        fsl,pins = <
            MX8MM_IOMUXC_GPIO1_IO12_GPIO1_IO12  0x1C0
        >;
    };
};
```

The `0x1C0` sets pull-up, hysteresis, and slew rate. The `IRQ_TYPE_EDGE_FALLING` tells the GPIO controller to generate an interrupt on the falling edge (button pressed, active low).

### Kernel Driver: Requesting the IRQ

In a custom driver, you request the GPIO and its interrupt using the descriptor-based API.

```c
#include <linux/gpio/consumer.h>
#include <linux/interrupt.h>
#include <linux/of.h>

struct my_device {
    struct gpio_desc *button_gpio;
    int irq;
};

static irqreturn_t button_isr(int irq, void *dev_id)
{
    struct my_device *dev = dev_id;
    // Top half: just schedule bottom half
    // Do NOT call printk here in production—too slow
    return IRQ_WAKE_THREAD;
}

static irqreturn_t button_threaded_isr(int irq, void *dev_id)
{
    struct my_device *dev = dev_id;
    int val;

    // Bottom half: can sleep, take mutexes
    val = gpiod_get_value(dev->button_gpio);
    dev_info(dev->dev, "Button state: %d\n", val);

    // Debounce: schedule a timer if needed
    // mod_timer(&dev->debounce_timer, jiffies + msecs_to_jiffies(50));

    return IRQ_HANDLED;
}

static int my_probe(struct platform_device *pdev)
{
    struct my_device *dev;
    int ret;

    dev = devm_kzalloc(&pdev->dev, sizeof(*dev), GFP_KERNEL);
    if (!dev)
        return -ENOMEM;

    dev->button_gpio = devm_gpiod_get(&pdev->dev, "button", GPIOD_IN);
    if (IS_ERR(dev->button_gpio))
        return PTR_ERR(dev->button_gpio);

    dev->irq = gpiod_to_irq(dev->button_gpio);
    if (dev->irq < 0)
        return dev->irq;

    ret = devm_request_threaded_irq(&pdev->dev, dev->irq,
                                    button_isr,          // top half
                                    button_threaded_isr, // bottom half
                                    IRQF_TRIGGER_FALLING | IRQF_ONESHOT,
                                    "user-button", dev);
    if (ret)
        return ret;

    platform_set_drvdata(pdev, dev);
    return 0;
}
```

Key points:
- `devm_request_threaded_irq` allocates both handlers. The `IRQF_ONESHOT` flag ensures the interrupt line is masked until the threaded handler finishes—critical for level-triggered interrupts.
- `gpiod_to_irq` translates the GPIO descriptor to a Linux IRQ number.
- The top half returns `IRQ_WAKE_THREAD` to invoke the bottom half.

### Checking Interrupts at Runtime

```bash
# See which GPIOs have interrupts registered
cat /proc/interrupts | grep gpio

# Check the GPIO chip details
cat /sys/kernel/debug/gpio

# Test with evtest (if using gpio-keys)
evtest /dev/input/event0
```

## Common Pitfalls & Gotchas

1. **Sleeping in atomic context.** The top half runs with interrupts disabled. Calling `gpiod_get_value` is fine (it’s a simple register read), but `i2c_transfer`, `msleep`, or `mutex_lock` will trigger a kernel splat. Always defer sleeping operations to the threaded handler or a workqueue.

2. **Missing IRQF_ONESHOT for threaded IRQs.** Without this flag, the interrupt line is re-enabled before the threaded handler runs. If the interrupt is level-triggered and the condition persists, you get an infinite interrupt storm. Always use `IRQF_ONESHOT` unless you have a specific reason not to.

3. **Debouncing in the wrong place.** Hardware debounce (RC filter or schmitt trigger) is best. If you must debounce in software, do it in the threaded handler with a timer, not in the top half. A common mistake is to add a `mdelay(10)` in the ISR—that blocks all other interrupts on that CPU for 10 ms.

## Try It Yourself

1. **Wire a button to a GPIO on your board** (e.g., GPIO1_12). Modify the device tree to add a `gpio-keys` node with `IRQ_TYPE_EDGE_BOTH`. Rebuild and boot. Use `evtest` to verify both press and release events appear.

2. **Write a minimal driver** that requests a GPIO as an interrupt using `devm_request_threaded_irq`. In the threaded handler, toggle an LED GPIO. Measure the latency from button press to LED toggle using an oscilloscope—aim for under 100 µs.

3. **Add software debounce** using a kernel timer. In the threaded handler, arm a timer for 50 ms. Only act on the button press if no new interrupt arrives within that window. Compare the behavior with and without debounce.

## Next Up

Tomorrow I’ll dive into the **DMA Engine API: Scatter-Gather & Cyclic Transfers**—how to move large buffers between memory and peripherals without burning CPU cycles, and why cyclic mode is essential for audio and waveform generation.
