---
title: "Day 08: State Machines for Driver Design: Table-Driven vs Switch-Based"
date: 2026-07-08
tags: ["til", "hal-patterns", "state-machine"]
---

## What I Explored Today

State machines are the backbone of virtually every peripheral driver I've ever written—from UART receivers to SPI transaction managers. Today I dug into the two dominant implementation strategies: the classic `switch`-based approach that everyone learns first, and the more advanced table-driven approach that scales better for complex drivers. I implemented both for a simulated I2C slave driver and compared them on code size, execution determinism, and maintainability. The results confirmed what I suspected: table-driven wins for anything beyond three states, but `switch`-based still has its place for simple, linear sequences.

## The Core Concept

A state machine in a driver context is simply a way to encode "what happens next" based on "what just happened" and "what the hardware is doing now." The *why* is critical: peripheral hardware is inherently asynchronous and stateful. A UART doesn't care about your main loop—it fires interrupts when a byte arrives, and your driver must track whether you're expecting a start bit, data bits, parity, or stop bits. Without explicit state management, you get race conditions, missed events, and corrupted data.

The `switch`-based approach is intuitive: each state is a `case` label, and transitions are explicit `break` or `return` statements. It works, but it couples state logic with transition logic in a way that makes adding new states or events painful—you end up editing multiple `case` blocks and hoping you didn't miss a transition.

The table-driven approach decouples state logic from transition logic. You define a table where each row is a `(current_state, event) -> (next_state, action)` mapping. The driver core is a single, generic dispatch function that indexes into this table. This makes the state machine data—not code—which means you can change behavior by modifying a table (or even loading it from flash at runtime) without touching the dispatch logic.

## Key Commands / Configuration / Code

Here's a concrete comparison using a simplified I2C slave driver that handles address match, data read, and data write states.

**Switch-based implementation (classic, but rigid):**

```c
typedef enum {
    I2C_STATE_IDLE,
    I2C_STATE_ADDR_ACK,
    I2C_STATE_DATA_TX,
    I2C_STATE_DATA_RX,
    I2C_STATE_STOP
} i2c_state_t;

i2c_state_t current_state = I2C_STATE_IDLE;

void i2c_slave_event_handler(i2c_event_t event, uint8_t byte) {
    switch (current_state) {
        case I2C_STATE_IDLE:
            if (event == I2C_EVT_START) {
                current_state = I2C_STATE_ADDR_ACK;
                // hardware: send ACK
            }
            break;
        case I2C_STATE_ADDR_ACK:
            if (event == I2C_EVT_ADDR_MATCH) {
                if (byte & 0x01) { // read request
                    current_state = I2C_STATE_DATA_TX;
                } else {            // write request
                    current_state = I2C_STATE_DATA_RX;
                }
            }
            break;
        case I2C_STATE_DATA_TX:
            if (event == I2C_EVT_TX_REQ) {
                // load byte from buffer, send
            } else if (event == I2C_EVT_STOP) {
                current_state = I2C_STATE_STOP;
            }
            break;
        // ... more cases
    }
}
```

**Table-driven implementation (scalable, data-oriented):**

```c
typedef enum {
    I2C_EVT_START,
    I2C_EVT_ADDR_MATCH,
    I2C_EVT_TX_REQ,
    I2C_EVT_RX_DONE,
    I2C_EVT_STOP,
    I2C_EVT_COUNT
} i2c_event_t;

typedef struct {
    i2c_state_t  next_state;
    void (*action)(i2c_event_t event, uint8_t byte);
} i2c_transition_t;

// Transition table: [current_state][event] -> {next_state, action}
static const i2c_transition_t transition_table[I2C_STATE_COUNT][I2C_EVT_COUNT] = {
    // I2C_STATE_IDLE
    [I2C_STATE_IDLE] = {
        [I2C_EVT_START]     = { .next_state = I2C_STATE_ADDR_ACK, .action = i2c_send_ack },
        [I2C_EVT_STOP]      = { .next_state = I2C_STATE_IDLE,    .action = NULL },
        // all other events: default to stay in IDLE, no action
    },
    // I2C_STATE_ADDR_ACK
    [I2C_STATE_ADDR_ACK] = {
        [I2C_EVT_ADDR_MATCH] = { .next_state = I2C_STATE_DATA_TX, .action = i2c_check_rw },
        // ... more transitions
    },
    // ... remaining states
};

void i2c_dispatch(i2c_event_t event, uint8_t byte) {
    // Bounds check (critical for safety)
    if (current_state >= I2C_STATE_COUNT || event >= I2C_EVT_COUNT) return;

    const i2c_transition_t *t = &transition_table[current_state][event];
    if (t->action) {
        t->action(event, byte);  // execute the action for this transition
    }
    current_state = t->next_state;  // state transition is atomic
}
```

The dispatch function is now a tight, predictable loop—no branching on state values. The table can be placed in flash (const) and even shared across multiple instances if you use a state pointer.

## Common Pitfalls & Gotchas

1. **Table size explosion for dense state machines.** A table with `N` states and `M` events requires `N × M` entries. For a UART with 8 states and 5 events, that's 40 entries—fine. But if you have 50 states and 20 events, you're looking at 1000 entries. In that case, use a sparse table (linked list of transitions) or a hash map. Don't blindly allocate a full 2D array.

2. **Action function pointer overhead.** Each table entry stores a function pointer (typically 4 bytes on ARM Cortex-M). If your MCU has tight flash, consider using an enum of action IDs and a separate dispatch switch for actions. This trades a small switch for smaller table entries (1 byte vs 4 bytes per action).

3. **Missing default transitions.** In the switch-based approach, you often forget to handle unexpected events in a state. The table-driven approach makes this explicit: you must fill every `(state, event)` pair. Use a macro or a sentinel value (like `{ .next_state = SAME, .action = NULL }`) to handle "ignore" transitions cleanly.

## Try It Yourself

1. **Refactor a simple UART driver** you've written from switch-based to table-driven. Start with just 4 states (IDLE, START_BIT, DATA_BITS, STOP_BIT) and 3 events (RISE_EDGE, FALL_EDGE, TIMEOUT). Measure the code size difference with `size` or your linker map.

2. **Add a new state** (e.g., PARITY_BIT) to both implementations. Time how long it takes to add it to the switch version vs the table version. Count the number of lines you had to change in each.

3. **Implement a guard condition** in the table-driven approach. Modify the `i2c_transition_t` struct to include a `bool (*guard)(void)` function pointer. Only execute the transition if the guard returns true. Use this to implement a "bus busy" check that prevents transitions when the bus is locked.

## Next Up

Tomorrow, I'll tackle the **Observer Pattern for Sensor Data & Event Callbacks**—how to decouple sensor drivers from application code so you can add new data consumers (logging, filtering, actuation) without touching the driver itself. We'll look at callback registration tables, weak-linkage patterns, and the trade-offs between polling and interrupt-driven observers.
