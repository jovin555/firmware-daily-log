---
title: "Day 14: UART Driver API: Async, Interrupt & Polling Modes"
date: 2026-06-26
tags: ["til", "zephyr", "uart", "serial"]
---

## What I Explored Today

Today I dug into Zephyr's UART driver API, specifically the three operational modes: polling, interrupt-driven, and asynchronous (DMA-based). While most embedded engineers are comfortable with `printf` over serial, Zephyr's UART subsystem exposes a rich, mode-switchable API that directly impacts throughput, CPU utilization, and power consumption. I focused on how to select the right mode for a given use case, the API contracts for each, and the common footguns that trip up developers moving from bare-metal or other RTOSes.

## The Core Concept

UART communication in Zephyr isn't one-size-fits-all. The API is designed around three distinct operational modes, each with a separate set of function pointers in the driver struct. You don't just "open" a UART; you choose a mode and stick with it until you reconfigure. The modes map directly to real-world constraints:

- **Polling mode** (`uart_poll_*`): Blocking, busy-wait. Use for debug output, bootloaders, or low-throughput paths where latency is acceptable. Zero interrupt overhead, but wastes CPU cycles.
- **Interrupt mode** (`uart_irq_*`): Non-blocking, callback-driven. The driver fires an interrupt on RX/TX events. You register callbacks, enable specific interrupts, and handle data in chunks. Good for moderate throughput (115200 baud and below) with bounded latency.
- **Async mode** (`uart_*` with `uart_callback_set`): DMA-backed, buffer-oriented. You submit buffers for TX/RX, and the driver notifies you on completion, errors, or half-full conditions. Ideal for high baud rates (921600+), large transfers, or when you want the CPU to sleep while the DMA engine moves bytes.

The critical insight: these modes are **mutually exclusive** for a given UART instance at runtime. You cannot mix `uart_poll_out` with an active async transfer. The API enforces this at the driver level, but the compiler won't catch it.

## Key Commands / Configuration / Code

### Device Tree & Kconfig

First, ensure your UART is enabled in the devicetree. For an STM32, it might look like:

```dts
&usart1 {
    status = "okay";
    current-speed = <115200>;
    pinctrl-0 = <&usart1_tx_pa9 &usart1_rx_pa10>;
    pinctrl-names = "default";
};
```

In `prj.conf`, enable the UART driver and the specific mode you need:

```kconfig
CONFIG_SERIAL=y
CONFIG_UART_INTERRUPT_DRIVEN=y   # for interrupt mode
CONFIG_UART_ASYNC_API=y          # for async mode
```

### Polling Mode (Simplest)

```c
#include <zephyr/device.h>
#include <zephyr/drivers/uart.h>

const struct device *uart_dev = DEVICE_DT_GET(DT_NODELABEL(usart1));

if (!device_is_ready(uart_dev)) {
    return;
}

// Blocking transmit
uart_poll_out(uart_dev, 'A');

// Blocking receive (returns -1 on timeout if no byte available)
unsigned char c;
int ret = uart_poll_in(uart_dev, &c);
if (ret == 0) {
    // process c
}
```

### Interrupt Mode (Callback-Driven)

```c
static void uart_irq_cb(const struct device *dev, void *user_data)
{
    if (!uart_irq_update(dev)) {
        return;  // spurious interrupt
    }

    if (uart_irq_rx_ready(dev)) {
        unsigned char c;
        while (uart_fifo_read(dev, &c, 1) == 1) {
            // push to ring buffer, etc.
        }
    }

    if (uart_irq_tx_ready(dev)) {
        // fill TX FIFO from buffer
        unsigned char data = get_next_tx_byte();
        uart_fifo_fill(dev, &data, 1);
    }
}

// In your init:
uart_irq_callback_set(uart_dev, uart_irq_cb);
uart_irq_rx_enable(uart_dev);
// uart_irq_tx_enable() when you have data to send
```

### Async Mode (DMA-Based)

```c
static uint8_t rx_buf[256];
static uint8_t tx_buf[] = "Hello from async UART!\r\n";

static void uart_async_cb(const struct device *dev,
                          struct uart_event *evt, void *user_data)
{
    switch (evt->type) {
    case UART_TX_DONE:
        // TX buffer consumed; can free or reuse
        break;
    case UART_RX_RDY:
        // evt->data.rx.buf, evt->data.rx.len, evt->data.rx.offset
        process_received_data(evt->data.rx.buf + evt->data.rx.offset,
                              evt->data.rx.len);
        break;
    case UART_RX_BUF_REQUEST:
        // Provide next buffer for continuous RX
        uart_rx_buf_rsp(dev, rx_buf, sizeof(rx_buf));
        break;
    case UART_RX_BUF_RELEASED:
        // Driver done with this buffer; can reuse
        break;
    case UART_RX_STOPPED:
        // Error or user-requested stop
        break;
    default:
        break;
    }
}

// In your init:
uart_callback_set(uart_dev, uart_async_cb, NULL);

// Start async RX (continuous mode with buffer request)
uart_rx_enable(uart_dev, rx_buf, sizeof(rx_buf), 100); // 100ms timeout

// Start async TX
uart_tx(uart_dev, tx_buf, sizeof(tx_buf), SYS_FOREVER_MS);
```

## Common Pitfalls & Gotchas

1. **Forgetting to call `uart_irq_update()` in interrupt callbacks.** This function synchronizes the interrupt status registers with the driver's internal state. Without it, `uart_irq_rx_ready()` may return stale values, causing missed bytes or infinite interrupt loops.

2. **Mixing modes on the same UART.** If you call `uart_poll_out()` while an async TX is in progress, the driver may corrupt internal state or silently drop bytes. Always ensure you've stopped the current mode (e.g., `uart_tx_abort()`) before switching.

3. **Async RX buffer starvation.** In continuous async RX mode, the driver requests new buffers via `UART_RX_BUF_REQUEST`. If you don't respond with `uart_rx_buf_rsp()` quickly enough, the driver will stop receiving data. For high baud rates, pre-allocate a pool of buffers and respond from the callback immediately.

4. **Interrupt priority and nesting.** UART interrupts often share priority levels with other peripherals. If your callback does heavy processing (e.g., parsing, memory allocation), you can starve lower-priority tasks or cause watchdog resets. Keep callbacks minimal; defer work to a thread.

## Try It Yourself

1. **Polling loopback:** Configure a UART in polling mode. Read a byte from the RX pin and echo it back on TX. Measure the maximum baud rate where this still works without dropping bytes (hint: it's lower than you think).

2. **Interrupt-driven ring buffer:** Implement a circular byte buffer in the UART IRQ callback. From a separate thread, periodically read from the buffer and print the number of bytes received per second. Compare CPU utilization vs. polling.

3. **Async DMA transfer:** Set up async mode with a 1 KB TX buffer. Use a logic analyzer or oscilloscope to measure the time between the last byte leaving the TX pin and the `UART_TX_DONE` callback firing. This reveals DMA descriptor overhead.

## Next Up

Tomorrow, we'll explore the **Sensor API: Generic Sensor Framework & SENSOR_CHAN**. We'll cover how Zephyr abstracts accelerometers, temperature sensors, and magnetometers behind a unified API, how to read sensor values with `sensor_sample_fetch()`, and the channel mapping that lets you write driver-agnostic sensor code.
