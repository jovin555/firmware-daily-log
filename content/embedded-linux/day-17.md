---
title: "Day 17: Memory Allocation: kmalloc, vmalloc, DMA Memory"
date: 2026-06-29
tags: ["til", "embedded-linux", "kmalloc", "vmalloc"]
---

## What I Explored Today

Today I dug into the three primary memory allocation APIs available to kernel module developers: `kmalloc`, `vmalloc`, and the DMA-specific allocation functions. While user-space developers have `malloc` and `mmap`, the kernel presents a more fragmented landscape because physical memory constraints, contiguous allocation requirements, and DMA bus addressing all matter deeply. I traced through the kernel source (`mm/slab.c`, `mm/vmalloc.c`, and `kernel/dma/`) to understand when each API is appropriate and, more importantly, when using the wrong one silently kills performance or crashes the system.

## The Core Concept

The fundamental tension in kernel memory allocation is between **physical contiguity** and **virtual contiguity**. User space never sees this — every pointer is virtual. But in the kernel:

- **kmalloc** guarantees physically contiguous memory, which is required for DMA transfers, hardware register access, and small structures that must fit in a single page. It allocates from the slab allocator (or slub/slob on smaller systems) and is fast, but limited to ~4 MB per allocation on most architectures.

- **vmalloc** allocates virtually contiguous memory that may be scattered across physical pages. This is great for large buffers (think video frame buffers or large hash tables) where you don't need DMA. The trade-off is slower access because each page may require a TLB miss and page table walk.

- **DMA memory** is a special case of physically contiguous memory that also meets bus address constraints. On systems with an IOMMU, this can be virtualized; on simpler embedded SoCs, you must allocate from a dedicated coherent pool or use streaming DMA mappings.

The rule of thumb: use `kmalloc` for anything under a page (4 KB) that touches hardware, `vmalloc` for large software-only buffers, and DMA APIs whenever data crosses the device boundary.

## Key Commands / Configuration / Code

### kmalloc — fast, contiguous, limited size

```c
#include <linux/slab.h>

struct my_device *dev;
// Allocate a small structure — physically contiguous, cache-aligned
dev = kmalloc(sizeof(*dev), GFP_KERNEL);
if (!dev)
    return -ENOMEM;

// For DMA-safe allocations, use GFP_DMA flag
dma_buf = kmalloc(4096, GFP_KERNEL | GFP_DMA);
// GFP_DMA restricts allocation to the first 16 MB (ISA DMA zone)
// On modern ARM64, this may be unnecessary — check your dma-ranges

kfree(dev);
kfree(dma_buf);
```

### vmalloc — large, virtually contiguous, slower

```c
#include <linux/vmalloc.h>

// Allocate a 1 MB buffer for a software framebuffer
unsigned char *fb = vmalloc(SZ_1M);
if (!fb)
    return -ENOMEM;

// Access is normal — but each page may be physically discontiguous
memset(fb, 0, SZ_1M);

vfree(fb);
```

### DMA coherent allocation — for streaming data to devices

```c
#include <linux/dma-mapping.h>
#include <linux/device.h>

struct device *dev = &pdev->dev;  // from platform driver
dma_addr_t dma_handle;
void *cpu_addr;
size_t size = SZ_64K;

// Allocate coherent memory — both CPU and device can access simultaneously
cpu_addr = dma_alloc_coherent(dev, size, &dma_handle, GFP_KERNEL);
if (!cpu_addr)
    return -ENOMEM;

// dma_handle is the bus address to program into the device
writel(dma_handle, dev->regs + DMA_ADDR_REG);

// ... use the buffer ...

dma_free_coherent(dev, size, cpu_addr, dma_handle);
```

### Check current allocation stats from /proc

```bash
# See slab cache usage (kmalloc pools)
cat /proc/slabinfo | head -20

# See vmalloc usage
cat /proc/vmallocinfo | head -10

# Check DMA pool usage (if CONFIG_DMA_API_DEBUG=y)
cat /sys/kernel/debug/dma-api/dump
```

## Common Pitfalls & Gotchas

1. **Using kmalloc for large buffers** — On a system with fragmented memory, `kmalloc(2 * PAGE_SIZE, GFP_KERNEL)` can fail even when plenty of free memory exists. The allocator needs physically contiguous pages, which become scarce after uptime. Always fall back to `vmalloc` or use `__get_free_pages` with `GFP_NOWARN` if you must have contiguity.

2. **Forgetting DMA coherency** — If you allocate a buffer with `kmalloc` and hand its physical address to a DMA engine without proper cache maintenance, you'll get data corruption. Use `dma_map_single()` for streaming mappings or `dma_alloc_coherent()` for coherent memory. On ARM, the cache is not automatically flushed for DMA.

3. **vmalloc in atomic context** — `vmalloc` can sleep (it may need to block for page table updates). Calling it from a spinlock or interrupt context will trigger a kernel BUG. Use `kmalloc(GFP_ATOMIC)` or a pre-allocated pool instead.

## Try It Yourself

1. **Write a kernel module that allocates a 4 KB buffer with kmalloc and a 1 MB buffer with vmalloc.** Print both virtual addresses and verify they are in different address ranges (`/proc/kallsyms` shows the vmalloc region starts at `VMALLOC_START`). Use `printk` to dump the physical address of the first page in each buffer.

2. **Simulate DMA allocation failure.** Modify a simple platform driver to call `dma_alloc_coherent()` for 4 MB on a system with limited CMA pool. Check `dmesg` for the allocation failure and verify the CMA size in `/proc/meminfo` under `CmaTotal` and `CmaFree`.

3. **Measure performance difference.** Write a test that writes 1 MB of data to a kmalloc'd buffer and a vmalloc'd buffer, timing each with `ktime_get()`. Run it on a system with heavy memory pressure (use a stress-ng VM stressor). Note the variance — vmalloc access time will spike due to TLB misses.

## Next Up

Tomorrow, I'll dive into the **MTD Subsystem: NAND, NOR & Flash Layers** — how the kernel abstracts raw flash devices, the difference between MTD and block layers, and why UBI/UBIFS exists for NAND management.
