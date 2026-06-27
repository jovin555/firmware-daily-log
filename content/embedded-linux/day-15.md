---
title: "Day 15: DMA Engine API: Scatter-Gather & Cyclic Transfers"
date: 2026-06-27
tags: ["til", "embedded-linux", "dma", "transfers"]
---

## What I Explored Today

Today I dove deep into the Linux DMA Engine API, specifically focusing on two advanced transfer modes that every embedded driver engineer needs to master: scatter-gather (SG) and cyclic transfers. While simple mem-to-mem or mem-to-device DMA is well documented, the real-world use cases—audio buffers, network packet processing, and video capture—demand non-contiguous memory handling and continuous streaming. I spent the morning tracing through `drivers/dma/` and testing with a TI AM62x platform, and the afternoon writing a test driver that exercises both modes.

## The Core Concept

The DMA Engine API abstracts away the hardware-specific DMA controller registers and interrupt handling, providing a unified interface for requesting channels, preparing descriptors, and submitting transfers. The two modes solve fundamentally different problems:

**Scatter-gather DMA** handles the case where your source or destination buffer is fragmented across physical memory. Instead of copying data into a contiguous bounce buffer (which wastes CPU cycles and memory bandwidth), you build a descriptor chain—each descriptor points to a different physical region. The DMA controller walks this chain autonomously, issuing interrupts only when the entire chain completes. This is critical for network drivers (fragmented sk_buffs) and filesystem I/O (page-cache pages).

**Cyclic DMA** is for continuous, periodic transfers where you never want the data stream to stop. Think audio playback: the DMA controller writes samples to a circular buffer, and when it wraps around, it fires an interrupt so you can refill the buffer. The key insight is that cyclic transfers have no "done" state—they run forever until explicitly terminated. The DMA engine API handles this by preparing a single descriptor that loops back on itself.

## Key Commands / Configuration / Code

Let's walk through a real driver snippet that registers a DMA channel and sets up both transfer types. I'm using the `dmaengine` subsystem, which is available on any modern kernel (4.19+).

```c
#include <linux/dmaengine.h>
#include <linux/dma-mapping.h>
#include <linux/slab.h>

struct my_dma_dev {
    struct dma_chan *chan;
    struct completion done;
};

/* Callback for scatter-gather completion */
static void sg_dma_callback(void *param)
{
    struct completion *done = param;
    complete(done);
}

/* Prepare and submit a scatter-gather transfer */
int my_sg_transfer(struct my_dma_dev *dev, struct scatterlist *sgl,
                   unsigned int sg_len, enum dma_transfer_direction dir)
{
    struct dma_async_tx_descriptor *tx;
    unsigned long flags = DMA_CTRL_ACK | DMA_PREP_INTERRUPT;

    /* Prepare the descriptor chain from the scatterlist */
    tx = dmaengine_prep_slave_sg(dev->chan, sgl, sg_len, dir, flags);
    if (!tx) {
        dev_err(dev->chan->device->dev, "Failed to prepare SG descriptor\n");
        return -ENOMEM;
    }

    /* Attach callback and submit */
    tx->callback = sg_dma_callback;
    tx->callback_param = &dev->done;
    dmaengine_submit(tx);

    /* Fire the transfer */
    dma_async_issue_pending(dev->chan);

    /* Wait for completion (in real code, use non-blocking) */
    wait_for_completion(&dev->done);
    return 0;
}

/* Cyclic transfer setup (e.g., for audio playback) */
int my_cyclic_transfer(struct my_dma_dev *dev, dma_addr_t buf_addr,
                       size_t buf_len, size_t period_len,
                       enum dma_transfer_direction dir)
{
    struct dma_async_tx_descriptor *tx;

    /* Prepare a cyclic descriptor — note: no flags for interrupt */
    tx = dmaengine_prep_dma_cyclic(dev->chan, buf_addr, buf_len,
                                   period_len, dir, 0);
    if (!tx) {
        dev_err(dev->chan->device->dev, "Failed to prepare cyclic descriptor\n");
        return -ENOMEM;
    }

    /* Cyclic transfers use a different callback mechanism */
    tx->callback = NULL;  /* Use dma_cookie for status polling */
    dmaengine_submit(tx);
    dma_async_issue_pending(dev->chan);

    /* Transfer runs until you call dmaengine_terminate_sync() */
    return 0;
}

/* Channel request example */
struct dma_chan *request_dma_channel(const char *chan_name)
{
    dma_cap_mask_t mask;
    dma_cap_zero(mask);
    dma_cap_set(DMA_SLAVE, mask);  /* We need slave DMA, not memcpy */

    /* Filter by device name or channel name */
    struct dma_slave_map map = {
        .devname = "42000000.dma-controller",
        .slave = chan_name,
    };

    return dma_request_slave_channel_compat(mask, dma_filter_fn,
                                            &map, NULL, "my_driver");
}
```

**Key configuration steps outside the code:**

1. **Device tree binding**: Ensure your DMA controller node has the correct `#dma-cells` and your peripheral node has a `dmas` and `dma-names` property.
2. **Channel allocation**: Always check `dmaengine_slave_config()` for bus width and burst size—mismatches cause silent data corruption.
3. **Buffer alignment**: Most DMA controllers require source/destination addresses to be aligned to the bus width (e.g., 4-byte alignment for 32-bit transfers).

## Common Pitfalls & Gotchas

1. **Forgetting to call `dma_map_sg()` before `dmaengine_prep_slave_sg()`**  
   The scatterlist you pass must be DMA-mapped. If you skip this, the DMA controller sees CPU virtual addresses, not physical addresses. The kernel will happily prepare the descriptor, but the transfer will access garbage memory. Always use `dma_map_sg(dev->dma_dev, sgl, sg_len, dir)` and check the return value.

2. **Cyclic transfer period size mismatch**  
   The period length must divide the total buffer length evenly. If `buf_len % period_len != 0`, `dmaengine_prep_dma_cyclic()` returns NULL. Worse, some controllers silently truncate the last period. Always validate at probe time.

3. **Interrupt storm from cyclic transfers**  
   Cyclic transfers fire an interrupt at the end of each period. If your period is too small (e.g., 64 bytes at 48 kHz audio), you'll get thousands of interrupts per second. Use `dmaengine_terminate_sync()` to stop cleanly, and consider using DMA's built-in interrupt coalescing if available.

## Try It Yourself

1. **Write a scatter-gather test driver**  
   Allocate two physically non-contiguous buffers using `alloc_pages()` (order > 0), build a scatterlist with `sg_set_page()`, and perform a DMA memcpy between them. Verify the data is correct after transfer.

2. **Modify an existing cyclic driver**  
   Take the kernel's `snd-soc-dmaengine-pcm.c` and change the period size from the default to a non-power-of-two value (e.g., 480 bytes). Observe what happens during playback—does the DMA controller handle it? Check `dmesg` for errors.

3. **Profile DMA latency**  
   Use `trace-cmd` to trace `dmaengine_prep_slave_sg`, `dmaengine_submit`, and the completion callback. Measure the time from submission to callback for a single SG descriptor vs. a chain of 10 descriptors. This reveals the overhead of descriptor chaining.

## Next Up

Tomorrow, we leave the DMA controller behind and enter the memory management unit. I'll cover how the Linux kernel uses virtual memory, page tables, and the MMU to isolate processes, handle memory-mapped I/O, and implement demand paging—essential knowledge for debugging mysterious kernel oopses and optimizing memory bandwidth in embedded systems.
