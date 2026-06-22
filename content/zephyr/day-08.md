---
title: "Day 08: Message Queues & Mailboxes: Thread Communication"
date: 2026-06-22
tags: ["til", "zephyr", "msgq", "ipc"]
---

## What I Explored Today

Today I dug into Zephyr's message queues (`k_msgq`) and mailboxes (`k_mbox`) — the two primary kernel objects for structured, asynchronous data transfer between threads. While FIFOs and LIFOs handle pointer-sized payloads, message queues and mailboxes support arbitrary-sized data blocks with built-in buffering. I focused on message queues for most of the day, since they're the workhorse for sensor data pipelines, command dispatch, and inter-core communication in production systems. Mailboxes, with their synchronous reply semantics, came into play for request-response patterns.

## The Core Concept

Message queues solve a fundamental problem: how do you pass structured data between threads without shared memory corruption or busy-waiting? The kernel provides a fixed-size, FIFO-ordered buffer where each element is a copy of the sender's data. This copy semantics is critical — the sender's stack buffer can be reused immediately after `k_msgq_put()` returns, and the receiver gets a private copy that won't be mutated by other threads.

The "why" here is deterministic behavior. Unlike a shared ring buffer with manual mutex protection, Zephyr's message queue integrates directly with the scheduler. A thread waiting on `k_msgq_get()` consumes zero CPU cycles until data arrives. When a message is enqueued, the kernel can immediately pend the highest-priority waiting thread. This is the difference between polling at 1 kHz and interrupt-driven delivery.

Mailboxes extend this with a rendezvous mechanism. When a sender calls `k_mbox_put()`, it can optionally block until a receiver processes the message and sends a reply. This is useful for RPC-style patterns where the sender needs confirmation or a result. However, mailboxes are more complex — they use a linked list of pending messages and support variable-length data via `k_mbox_msg` descriptors.

## Key Commands / Configuration / Code

**Message Queue Definition and Initialization**

```c
// Static definition with 10 elements, each 32 bytes
K_MSGQ_DEFINE(sensor_data_q, 32, 10, 4);
// Parameters: name, element_size, max_elements, alignment

// Dynamic initialization (useful when size is runtime-configurable)
struct k_msgq temp_q;
char __aligned(4) temp_buffer[20 * sizeof(struct measurement)];

void init_temp_q(void)
{
    k_msgq_init(&temp_q, temp_buffer, sizeof(struct measurement), 20);
}
```

**Sender Thread — Periodic Sensor Read**

```c
struct sensor_reading {
    uint16_t id;
    uint32_t timestamp;
    float temperature;
    float humidity;
};

void sensor_thread(void *arg1, void *arg2, void *arg3)
{
    struct sensor_reading reading;
    int ret;

    while (1) {
        read_sensor(&reading);
        reading.timestamp = k_uptime_get_32();

        // k_msgq_put with K_NO_WAIT — non-blocking, drops if full
        ret = k_msgq_put(&sensor_data_q, &reading, K_NO_WAIT);
        if (ret != 0) {
            // Queue full — log overflow, increment counter
            stats.overflow_count++;
        }

        k_sleep(K_MSEC(100));
    }
}
```

**Receiver Thread — Processing with Timeout**

```c
void processing_thread(void *arg1, void *arg2, void *arg3)
{
    struct sensor_reading reading;
    int ret;

    while (1) {
        // Block up to 500 ms for a message
        ret = k_msgq_get(&sensor_data_q, &reading, K_MSEC(500));
        if (ret == 0) {
            process_reading(&reading);
        } else {
            // Timeout — no data available, maybe enter low-power mode
            enter_idle();
        }
    }
}
```

**Mailbox — Request-Response Pattern**

```c
struct command_msg {
    uint32_t cmd_id;
    uint8_t payload[64];
};

struct response_msg {
    int32_t status;
    uint32_t result;
};

K_MBOX_DEFINE(cmd_mbox);

// Sender (blocks until reply received)
void command_sender(void)
{
    struct k_mbox_msg send_msg, reply_msg;
    struct command_msg cmd = { .cmd_id = 0x01 };
    struct response_msg resp;

    send_msg.info = sizeof(cmd);
    send_msg.size = sizeof(cmd);
    send_msg.tx_data = &cmd;
    send_msg.tx_block.data = NULL;  // using tx_data, not memory pool block
    send_msg.rx_data = &resp;
    send_msg.rx_size = sizeof(resp);

    k_mbox_put(&cmd_mbox, &send_msg, K_SECONDS(1));
    // After return, resp contains the reply
    printk("Response status: %d\n", resp.status);
}
```

**ISR-to-Thread via Message Queue**

```c
void uart_isr(const struct device *dev)
{
    uint8_t byte;
    while (uart_fifo_read(dev, &byte, 1) == 1) {
        // From ISR — must use K_NO_WAIT
        k_msgq_put(&uart_rx_q, &byte, K_NO_WAIT);
    }
}
```

## Common Pitfalls & Gotchas

**1. Message Queue Full — Silent Data Loss**
The most common bug is using `K_NO_WAIT` in a producer thread and ignoring the return value. When the queue is full, `k_msgq_put()` returns `-ENOMSG` and the message is silently dropped. Always check the return code, or use `K_FOREVER` if the producer can block. For ISR producers, you have no choice but to drop — but you must increment an overflow counter for diagnostics.

**2. Alignment Mismatch on Message Data**
`K_MSGQ_DEFINE` accepts an alignment parameter (default 4). If your message struct contains 8-byte types like `uint64_t` or `double`, you need `__aligned(8)` on the struct and alignment=8 in the macro. Misaligned access on Cortex-M0 or other non-unaligned architectures causes a hard fault. I've debugged this at 2 AM — it's not fun.

**3. Mailbox Memory Pool Leaks**
Mailboxes can use kernel memory pools for data transfer (`tx_block` field). If the receiver never calls `k_mbox_get()` or the message times out, the memory pool block is leaked. Always ensure your receiver thread is responsive, and consider using `tx_data` (stack copy) instead of `tx_block` for simple cases to avoid pool management entirely.

## Try It Yourself

**Task 1: Sensor Data Pipeline**
Create two threads: a producer that generates 1000 random temperature readings per second, and a consumer that averages batches of 10 readings. Use a `k_msgq` with 20 elements. Add a third "monitor" thread that prints the queue fill level every second using `k_msgq_num_used_get()`.

**Task 2: Command-Response with Mailbox**
Implement a simple command handler thread that accepts `struct { uint8_t opcode; uint16_t arg; }` via mailbox. The handler executes the operation (e.g., set LED brightness, read ADC) and replies with `struct { int32_t status; uint32_t value; }`. Write a sender that issues three different commands and validates the responses.

**Task 3: ISR Overflow Detection**
Modify an existing UART driver to push received bytes into a message queue. In the receiver thread, check `k_msgq_num_free_get()` before each read. If free space drops below 25%, toggle a GPIO to indicate "buffer pressure." This is exactly how production telemetry systems detect backpressure.

## Next Up

Tomorrow we'll cover FIFOs, LIFOs, and ring buffers — the lightweight, pointer-based cousins of message queues. FIFOs give you linked-list queuing with zero-copy semantics, LIFOs provide stack-like behavior for deferred work, and ring buffers offer lockless single-producer/single-consumer patterns ideal for ISR-to-thread handoff. We'll compare their performance characteristics and when to choose each over `k_msgq`.
