---
title: "Day 11: GPIO Driver API: Input, Output, Interrupts"
date: 2026-06-23
tags: ["til", "zephyr", "gpio", "drivers"]
---

## What I Explored Today

Today I dove into Zephyr's GPIO driver API, which is one of the most fundamental hardware abstraction layers in the RTOS. After spending days on kernel primitives, it was refreshing to touch actual pins. I worked through configuring GPIOs as outputs to drive LEDs, inputs to read button states, and—most critically—setting up edge-triggered interrupts with proper callback handling. The API is clean but has sharp edges, especially around devicetree pin configuration and interrupt context restrictions.

## The Core Concept

GPIO control in Zephyr isn't just about toggling a register. The API is designed around three core operations: **configuration**, **state I/O**, and **interrupt management**. The why behind this design is portability and safety.

First, configuration is decoupled from operation. You call `gpio_pin_configure()` once to set direction, pull-up/down, and interrupt trigger. This forces you to think about pin state before using it—preventing the common embedded bug of reading an uninitialized input.

Second, the API enforces a clear separation between synchronous and asynchronous I/O. For outputs, you use `gpio_pin_set()` or `gpio_port_set_masked()`. For inputs, you poll with `gpio_pin_get()`. But when you need responsiveness without busy-waiting, you switch to interrupt mode with `gpio_pin_interrupt_configure()` and a callback.

Third, interrupts are handled through a callback mechanism that runs in interrupt context. This means you cannot block, allocate memory, or call most kernel APIs inside the callback. Instead, you're expected to defer work to a thread using a semaphore or work queue. This pattern—interrupt fires, signals a thread, thread does the heavy lifting—is the bedrock of real-time embedded design.

## Key Commands / Configuration / Code

Let's walk through a complete example: reading a button with a falling-edge interrupt and toggling an LED.

First, the devicetree overlay (for an nRF52840 DK):

```dts
/ {
    gpio_keys {
        compatible = "gpio-keys";
        button0: button_0 {
            gpios = <&gpio0 11 (GPIO_PULL_UP | GPIO_ACTIVE_LOW)>;
            label = "Push button 1";
        };
    };

    gpio_leds {
        compatible = "gpio-leds";
        led0: led_0 {
            gpios = <&gpio0 13 GPIO_ACTIVE_LOW>;
            label = "Green LED 0";
        };
    };
};
```

Now the C code:

```c
#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/sys/printk.h>

/* Get devicetree aliases */
#define LED0_NODE DT_ALIAS(led0)
#define BUTTON0_NODE DT_ALIAS(sw0)

static const struct gpio_dt_spec led = GPIO_DT_SPEC_GET(LED0_NODE, gpios);
static const struct gpio_dt_spec button = GPIO_DT_SPEC_GET(BUTTON0_NODE, gpios);

/* Semaphore to defer work from ISR */
static struct k_sem button_sem;

/* Interrupt callback — runs in ISR context */
void button_pressed(const struct device *dev, struct gpio_callback *cb,
                    uint32_t pins)
{
    /* Signal the worker thread — do NOT call printk or gpio here */
    k_sem_give(&button_sem);
}

/* Worker thread */
void button_thread(void *arg1, void *arg2, void *arg3)
{
    while (1) {
        k_sem_take(&button_sem, K_FOREVER);
        gpio_pin_toggle_dt(&led);
        printk("Button pressed, LED toggled\n");
    }
}

/* Callback structure — must be statically allocated */
static struct gpio_callback button_cb_data;

void main(void)
{
    int ret;

    /* Verify devices are ready */
    if (!device_is_ready(led.port) || !device_is_ready(button.port)) {
        return;
    }

    /* Configure LED as output */
    ret = gpio_pin_configure_dt(&led, GPIO_OUTPUT_ACTIVE);
    if (ret < 0) return;

    /* Configure button as input with pull-up */
    ret = gpio_pin_configure_dt(&button, GPIO_INPUT);
    if (ret < 0) return;

    /* Initialize semaphore */
    k_sem_init(&button_sem, 0, 1);

    /* Set up interrupt on falling edge */
    ret = gpio_pin_interrupt_configure_dt(&button, GPIO_INT_EDGE_FALLING);
    if (ret < 0) return;

    /* Initialize callback and add it to the device */
    gpio_init_callback(&button_cb_data, button_pressed, BIT(button.pin));
    gpio_add_callback(button.port, &button_cb_data);

    /* Start worker thread */
    k_thread_create(&my_thread, stack_area, STACK_SIZE,
                    button_thread, NULL, NULL, NULL,
                    5, 0, K_NO_WAIT);

    while (1) {
        k_sleep(K_FOREVER);
    }
}
```

Key points:
- `gpio_dt_spec` bundles the port device, pin number, and flags from devicetree.
- `_dt` suffix functions use the spec directly—prefer these over raw `gpio_pin_configure()`.
- Interrupt callbacks must be fast and non-blocking.
- `BIT(button.pin)` tells the callback which pin triggered it.

## Common Pitfalls & Gotchas

**1. Forgetting to enable interrupt in devicetree.** If your pin doesn't have an `interrupts` property in the devicetree, `gpio_pin_interrupt_configure_dt()` may silently fail. Always check the return value—it's not optional.

**2. Calling GPIO functions inside the interrupt callback.** The GPIO driver itself may use spinlocks or mutexes. Calling `gpio_pin_set()` from within a callback can cause a deadlock if the same driver instance is accessed. Use the semaphore/workqueue pattern shown above.

**3. Misunderstanding active-low vs. active-high.** `GPIO_ACTIVE_LOW` means the pin is considered "asserted" when at 0V. If you read `gpio_pin_get()` on an active-low input, it returns 1 when the button is *not* pressed. This trips up everyone at least once. Use `gpio_pin_get_dt()` which respects the flags.

## Try It Yourself

1. **Debounce a button in software.** Modify the example to add a 50ms debounce timer in the worker thread. Use `k_timer_start()` and check the button state again before toggling the LED.

2. **Read a bank of 4 DIP switches.** Configure 4 pins as inputs with pull-ups. Use `gpio_port_get()` to read all pins at once, then print the 4-bit value as a hex digit every second.

3. **Implement a long-press detector.** Configure a button interrupt on both edges. In the callback, record the timestamp with `k_uptime_get()`. In the worker thread, if the button was held for >2 seconds, toggle a different LED.

## Next Up

Tomorrow I'll tackle the **I2C Driver API: Controller & Target Mode**. We'll configure an I2C controller to talk to a sensor, handle clock stretching, and implement a simple target (slave) responder. Bring your pull-up resistors.
