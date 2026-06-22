---
title: "Day 09: FIFOs, LIFOs & Ring Buffers"
date: 2026-06-22
tags: ["til", "zephyr", "fifo", "lifo", "buffers"]
---

## What I Explored Today

Today I dug into Zephyr's data-passing primitives: FIFOs, LIFOs, and ring buffers. These are the workhorses for moving data between threads and ISRs without shared-memory headaches. While message queues get all the attention, FIFOs and LIFOs offer lower overhead for pointer-based transfers, and ring buffers provide lock-free byte-stream handling. I spent the morning stress-testing these on an nRF52840, and the performance differences are stark.

## The Core Concept

The fundamental distinction is *ownership semantics*. FIFOs and LIFOs transfer ownership of a memory block (a `k_fifo` or `k_lifo` node) from one context to another. The data itself isn't copied — just a pointer. This makes them incredibly fast for passing large structures, but it means you must carefully manage memory allocation and lifetime.

Ring buffers (`ring_buf`) are different: they copy bytes into a pre-allocated circular buffer. There's no dynamic allocation, no pointer handoff — just raw data in, raw data out. This makes them ideal for ISR-to-thread byte streams (like UART RX) where you want zero allocation overhead and deterministic behavior.

**When to use what:**
- **FIFO**: First-in-first-out, thread-safe, blocking/non-blocking. Use for ordered work items, command queues.
- **LIFO**: Last-in-first-out, same API as FIFO. Use for stack-like patterns, free-list management.
- **Ring buffer**: Byte-oriented, fixed-size, ISR-safe. Use for serial data, audio buffers, sensor streams.

## Key Commands / Configuration / Code

### FIFO/LIFO Basics

```c
#include <zephyr/kernel.h>

/* Define a data structure that embeds a sys_snode_t */
struct data_item {
    sys_snode_t node;
    uint32_t value;
    uint8_t payload[64];
};

/* Declare a FIFO (LIFO uses K_LIFO_DEFINE) */
K_FIFO_DEFINE(my_fifo);

/* Producer thread */
void producer_thread(void *arg1, void *arg2, void *arg3)
{
    struct data_item *item;

    while (1) {
        /* Allocate from a memory pool or k_malloc */
        item = k_malloc(sizeof(struct data_item));
        if (!item) {
            continue;
        }

        item->value = some_sensor_reading();

        /* Enqueue — non-blocking, always succeeds */
        k_fifo_put(&my_fifo, &item->node);

        k_sleep(K_MSEC(100));
    }
}

/* Consumer thread */
void consumer_thread(void *arg1, void *arg2, void *arg3)
{
    struct data_item *item;

    while (1) {
        /* Block until data arrives */
        item = k_fifo_get(&my_fifo, K_FOREVER);
        if (item) {
            process_data(item->value);
            k_free(item);  /* MUST free after use */
        }
    }
}
```

### Ring Buffer Usage

```c
#include <zephyr/sys/ring_buffer.h>

/* Declare ring buffer with 256-byte capacity */
uint8_t rb_buffer[256];
struct ring_buf rb;

void init_ring_buffer(void)
{
    ring_buf_init(&rb, sizeof(rb_buffer), rb_buffer);
}

/* ISR context — put data */
void uart_isr(const struct device *dev)
{
    uint8_t byte;
    while (uart_fifo_read(dev, &byte, 1) == 1) {
        /* Returns bytes actually written */
        ring_buf_put(&rb, &byte, 1);
    }
}

/* Thread context — get data */
void uart_consumer_thread(void *arg1, void *arg2, void *arg3)
{
    uint8_t buf[32];
    uint32_t bytes_read;

    while (1) {
        bytes_read = ring_buf_get(&rb, buf, sizeof(buf));
        if (bytes_read > 0) {
            process_uart_data(buf, bytes_read);
        }
        k_sleep(K_MSEC(10));
    }
}
```

### Configuration

In `prj.conf`:
```conf
# Enable ring buffer support (usually on by default)
CONFIG_RING_BUFFER=y

# For dynamic allocation in FIFO/LIFO
CONFIG_HEAP_MEM_POOL_SIZE=4096
```

## Common Pitfalls & Gotchas

1. **Forgetting to free FIFO/LIFO nodes**: The kernel does NOT free memory. If you `k_fifo_put()` a `k_malloc()`'d node, you *must* `k_free()` it after `k_fifo_get()`. Leak a node every 100ms and you'll OOM in minutes.

2. **Ring buffer overflow is silent**: `ring_buf_put()` returns the number of bytes actually written. If the buffer is full, it returns 0 — no error, no blocking. Always check the return value, or use `ring_buf_put_claim()` for atomic multi-byte writes.

3. **FIFO/LIFO nodes must be aligned**: The `sys_snode_t` field must be the first member of your struct (or at a known offset). The kernel casts your struct to `sys_snode_t*` — if the layout is wrong, you corrupt the linked list. Always embed `sys_snode_t` as the first field.

4. **ISR safety**: `k_fifo_put()` and `k_lifo_put()` are ISR-safe. `k_fifo_get()` is NOT — never call blocking get from an ISR. Ring buffer `put`/`get` are fully ISR-safe (no kernel calls).

## Try It Yourself

1. **FIFO stress test**: Create two threads — one producer that puts 1000 items into a FIFO as fast as possible, one consumer that gets and frees them. Measure throughput with `k_cycle_get_32()`.

2. **Ring buffer ISR pattern**: Connect a UART interrupt that feeds bytes into a ring buffer. Create a thread that reads the ring buffer every 10ms and prints received bytes. Test with a serial terminal sending bursts.

3. **LIFO free-list**: Implement a memory pool using a LIFO. Pre-allocate 10 structs, push them onto a LIFO at init. Threads "allocate" by popping from the LIFO and "free" by pushing back. No heap fragmentation.

## Next Up

Tomorrow: **Timers & Delayed Work: k_timer, k_work** — we'll cover one-shot and periodic timers, the workqueue API for deferring work from ISRs, and how to avoid the classic "timer callback in ISR context" trap that bricks half the boards I've debugged.
