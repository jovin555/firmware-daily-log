---
title: "Day 12: Use-After-Free & Memory Corruption in Bare-Metal Systems"
date: 2026-07-12
tags: ["til", "threat-modeling", "uaf", "memory-corruption"]
---

## What I Explored Today

Today I dug into use-after-free (UAF) vulnerabilities in bare-metal firmware — not the heap-heavy, glibc-centric exploits you see in Linux, but the kind that bite you when you’re managing static pools, DMA buffers, and interrupt-driven deallocation. In a bare-metal system, there’s no OS to catch a double-free or invalid pointer dereference. A single UAF can corrupt a critical control structure, silently flip a flag, or cause a watchdog reset that erases forensic evidence. I spent the afternoon instrumenting a simple RTOS task scheduler to trace exactly how a freed memory block can be reused by an allocator while a dangling pointer still references it.

## The Core Concept

Use-after-free occurs when a program continues to use a pointer after the memory it points to has been freed and potentially reallocated. In bare-metal systems, the consequences are amplified because:

1. **No virtual memory** — every address is physical. A freed buffer might be reused for a DMA descriptor or a task control block (TCB).
2. **No memory protection unit (MPU) guard** — unless you explicitly configure regions, the CPU will happily read/write stale pointers.
3. **Interrupts can race** — a deferred interrupt handler might access a buffer that the main loop just freed.

The root cause is almost always a broken ownership model. In a typical RTOS, a task might allocate a message buffer, post it to a queue, and then free it — but the receiving task still holds a pointer. Or a DMA completion callback frees a buffer while the peripheral is still writing to it. The fix isn’t just “don’t free twice”; it’s about establishing clear, enforced ownership semantics at the code level.

## Key Commands / Configuration / Code

Let’s look at a realistic bare-metal memory pool and the UAF bug that lurks inside.

```c
// Simple fixed-block memory pool for a Cortex-M4 RTOS
#define POOL_SIZE 16
#define BLOCK_SIZE 64

typedef struct {
    uint32_t pool[POOL_SIZE][BLOCK_SIZE / sizeof(uint32_t)];
    uint32_t free_mask;  // bitmask: 1 = free, 0 = allocated
} mem_pool_t;

static mem_pool_t dma_pool;

void pool_init(mem_pool_t *p) {
    p->free_mask = 0xFFFFFFFF;  // all blocks free
}

void* pool_alloc(mem_pool_t *p) {
    uint32_t bit = __CLZ(__RBIT(p->free_mask));  // find first free bit
    if (bit >= POOL_SIZE) return NULL;
    p->free_mask &= ~(1UL << bit);               // mark allocated
    return &p->pool[bit];
}

void pool_free(mem_pool_t *p, void *ptr) {
    uint32_t idx = ((uint32_t)ptr - (uint32_t)p->pool) / BLOCK_SIZE;
    if (idx >= POOL_SIZE) return;                // bounds check
    p->free_mask |= (1UL << idx);                // mark free
}
```

**The UAF scenario:**

```c
// UAF bug: interrupt handler frees buffer, main loop still uses it
static uint8_t *rx_buffer = NULL;

void dma_rx_complete_isr(void) {
    // ISR frees the buffer after DMA finishes
    pool_free(&dma_pool, rx_buffer);
    rx_buffer = NULL;  // good practice, but too late if main loop already has pointer
}

void main_loop(void) {
    rx_buffer = (uint8_t*)pool_alloc(&dma_pool);
    start_dma_receive(rx_buffer, BLOCK_SIZE);
    
    while (dma_busy) {
        // wait
    }
    
    // BUG: rx_buffer might have been freed by ISR and reallocated
    // Writing to it now corrupts whatever owns the block
    memcpy(some_other_struct, rx_buffer, BLOCK_SIZE);
}
```

**The fix — use a flag or disable the ISR during access:**

```c
volatile bool buffer_freed = false;

void dma_rx_complete_isr(void) {
    pool_free(&dma_pool, rx_buffer);
    buffer_freed = true;  // signal main loop
}

void main_loop(void) {
    rx_buffer = (uint8_t*)pool_alloc(&dma_pool);
    start_dma_receive(rx_buffer, BLOCK_SIZE);
    
    while (dma_busy) {
        // wait
    }
    
    __disable_irq();
    if (!buffer_freed) {
        memcpy(some_other_struct, rx_buffer, BLOCK_SIZE);
    }
    __enable_irq();
}
```

## Common Pitfalls & Gotchas

1. **Assuming `NULL`-check after free is sufficient.**  
   Setting a pointer to `NULL` after `pool_free()` only prevents *your* code from using it. If another task or ISR holds a copy of the original pointer (aliasing), it will still dereference stale memory. Always audit pointer aliasing in your system.

2. **Forgetting that DMA or peripheral can write after logical “free.”**  
   A DMA transfer might still be in-flight when you free the buffer. The peripheral doesn’t know about your memory manager. Always ensure the DMA channel is disabled and any pending transfers are flushed before freeing the buffer. On Cortex-M, this means clearing the enable bit and reading the channel status register.

3. **Interrupt masking is not a silver bullet.**  
   Disabling interrupts around critical sections works, but it increases latency and can mask deeper race conditions. A better pattern is to use a deferred interrupt handler (e.g., a software timer callback) that runs at task level, not ISR level, to perform deallocation.

## Try It Yourself

1. **Instrument a static pool allocator** in your current bare-metal project. Add a “poison” pattern (e.g., `0xDEADBEEF`) to freed blocks and log a warning if any block is freed twice or if a freed block’s pattern is overwritten before reallocation.

2. **Write a test that simulates a UAF race.** Create two tasks: one that allocates a buffer, fills it with a known pattern, and frees it; another that continuously reads from a global pointer to that buffer. Use a logic analyzer or GPIO toggle to measure how long it takes for corruption to appear.

3. **Audit your DMA buffer lifecycle.** For every DMA buffer in your system, draw a state machine showing: allocated → in-use (DMA active) → consumed → freed. Mark which execution context (ISR, main loop, task) transitions each state. Identify any state where two contexts can access the buffer simultaneously.

## Next Up

Tomorrow, we’ll step back and look at the big picture: **MISRA C:2012: Rule Categories & Security Rationale**. We’ll break down the 16 rule categories, which ones directly prevent memory corruption, and how to apply them without drowning in false positives.
