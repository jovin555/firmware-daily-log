---
title: "Day 13: SPI Driver API: Full-Duplex & DMA Transfers"
date: 2026-06-25
tags: ["til", "zephyr", "spi", "dma"]
---

## What I Explored Today

Today I dove into Zephyr's SPI driver API, specifically focusing on full-duplex transfers and DMA-based operation. While SPI itself is a straightforward synchronous serial protocol, Zephyr's abstraction layer introduces several nuances around buffer management, chip select control, and DMA integration that can trip up even experienced engineers. I worked through the `spi_transceive()` API, configured DMA-backed transfers on an STM32L4, and validated timing with a logic analyzer.

## The Core Concept

SPI in Zephyr is fundamentally a full-duplex protocol—every byte shifted out on MOSI simultaneously shifts a byte in on MISO. The API reflects this: you always provide both a TX buffer and an RX buffer, even if you only care about one direction. The `spi_transceive()` function is the workhorse, handling synchronous, asynchronous, and DMA-driven transfers based on how you configure the buffers and the controller.

The key design decision in Zephyr is that the SPI driver does not manage chip select (CS) automatically in all configurations. You must explicitly control CS via GPIO, or rely on the controller's hardware CS if the driver supports it. This is a common source of bugs—forgetting to de-assert CS after a transaction leaves the slave in an undefined state.

DMA transfers are not magic; they require careful alignment of buffer memory (often to cache-line boundaries) and proper configuration of the DMA controller's channel, priority, and transfer width. Zephyr's device tree handles most of the static configuration, but runtime buffer management is on you.

## Key Commands / Configuration / Code

### Device Tree Configuration (STM32L4 example)

```dts
&spi1 {
    compatible = "st,stm32-spi";
    pinctrl-0 = <&spi1_sck_pa5 &spi1_miso_pa6 &spi1_mosi_pa7>;
    pinctrl-names = "default";
    cs-gpios = <&gpioa 4 GPIO_ACTIVE_LOW>;
    dmas = <&dma1 3 0x404>, <&dma1 2 0x404>;  /* TX: ch3, RX: ch2 */
    dma-names = "tx", "rx";
    status = "okay";
};
```

### Runtime SPI Configuration

```c
#include <zephyr/drivers/spi.h>

const struct device *spi_dev = DEVICE_DT_GET(DT_NODELABEL(spi1));

struct spi_config spi_cfg = {
    .frequency = 1000000,          // 1 MHz
    .operation = SPI_OP_MODE_MASTER | SPI_WORD_SET(8) | SPI_TRANSFER_MSB,
    .slave = 0,                    // CS index (if using hardware CS)
    .cs = NULL,                    // Use GPIO CS from devicetree
};

// Verify device is ready
if (!device_is_ready(spi_dev)) {
    printk("SPI device not ready\n");
    return -ENODEV;
}
```

### Full-Duplex Transfer with DMA

```c
int spi_full_duplex_dma(const struct device *spi_dev, struct spi_config *cfg,
                        uint8_t *tx_buf, uint8_t *rx_buf, size_t len)
{
    // Buffers must be DMA-accessible (no stack, no flash)
    // Use k_malloc() or static buffers with proper alignment
    struct spi_buf tx_bufs = {
        .buf = tx_buf,
        .len = len,
    };
    struct spi_buf rx_bufs = {
        .buf = rx_buf,
        .len = len,
    };
    struct spi_buf_set tx = { .buffers = &tx_bufs, .count = 1 };
    struct spi_buf_set rx = { .buffers = &rx_bufs, .count = 1 };

    // DMA is used automatically if the driver supports it
    // and the buffers are in DMA-able memory
    int ret = spi_transceive(spi_dev, cfg, &tx, &rx);
    if (ret < 0) {
        printk("SPI transceive failed: %d\n", ret);
    }
    return ret;
}
```

### Asynchronous Transfer with Callback

```c
static struct k_sem spi_sem;

static void spi_callback(const struct device *dev, int result, void *user_data)
{
    k_sem_give(&spi_sem);
}

int spi_async_transfer(const struct device *spi_dev, struct spi_config *cfg,
                       uint8_t *tx_buf, uint8_t *rx_buf, size_t len)
{
    struct spi_buf tx_bufs = { .buf = tx_buf, .len = len };
    struct spi_buf rx_bufs = { .buf = rx_buf, .len = len };
    struct spi_buf_set tx = { .buffers = &tx_bufs, .count = 1 };
    struct spi_buf_set rx = { .buffers = &rx_bufs, .count = 1 };

    struct spi_callback cb = {
        .callback = spi_callback,
        .user_data = NULL,
    };
    spi_callback_setup(spi_dev, &cb);

    k_sem_init(&spi_sem, 0, 1);
    int ret = spi_transceive_async(spi_dev, cfg, &tx, &rx);
    if (ret < 0) return ret;

    // Wait for completion (with timeout)
    ret = k_sem_take(&spi_sem, K_MSEC(100));
    if (ret < 0) {
        spi_transceive_async_cancel(spi_dev);
        return -ETIMEDOUT;
    }
    return 0;
}
```

## Common Pitfalls & Gotchas

1. **Buffer memory must be DMA-safe.** Stack-allocated buffers or buffers in flash will cause silent data corruption or hard faults when DMA is enabled. Always use `k_malloc()`, static globals, or memory from a DMA-capable heap. On Cortex-M, ensure buffers are aligned to 32 bytes (cache line) if data cache is enabled.

2. **Chip select management is your responsibility.** Many Zephyr SPI drivers do not automatically toggle CS between transactions. If you use GPIO-based CS, you must assert it before `spi_transceive()` and de-assert it after. For multi-byte transfers, keep CS asserted across the entire transaction by using a single `spi_transceive()` call with the full buffer.

3. **`spi_transceive()` is blocking by default.** Even with DMA, the function blocks until the transfer completes. If you need non-blocking behavior, you must use `spi_transceive_async()` with a callback. The DMA only accelerates the data movement, not the API semantics.

## Try It Yourself

1. **Verify DMA is actually being used.** Add `CONFIG_SPI_DMA=y` to your `prj.conf`, then instrument your SPI transfer with `k_cycle_get_32()` before and after `spi_transceive()`. Compare the cycle count with DMA enabled vs. disabled (by removing the `dmas` property from the devicetree). You should see a 5-10x improvement for transfers >64 bytes.

2. **Implement a multi-byte register read.** Connect an SPI flash or sensor. Write a function that asserts CS, sends a command byte, then reads N data bytes in a single `spi_transceive()` call. Use a logic analyzer to confirm CS stays low for the entire transaction.

3. **Stress-test buffer alignment.** Create a buffer that is intentionally misaligned (e.g., `uint8_t buf[17]` on a 4-byte aligned stack). Run 1000 SPI transfers and check for data corruption. Then fix the alignment with `__attribute__((aligned(32)))` and verify the corruption disappears.

## Next Up

Tomorrow we tackle **UART Driver API: Async, Interrupt & Polling Modes**—covering the three operational modes, ring buffer management, and how to avoid the dreaded UART overrun on high-speed links.
