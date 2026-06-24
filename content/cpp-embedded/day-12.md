---
title: "Day 12: State Machines in C++: enum class & std::variant FSMs"
date: 2026-06-24
tags: ["til", "cpp-embedded", "state-machine", "fsm"]
---

## What I Explored Today

Today I dug into two modern C++ approaches for implementing state machines in embedded systems: the classic `enum class`-based FSM and the more advanced `std::variant`-based FSM. While state machines are nothing new in embedded (we've been doing them with `switch` statements and function pointers for decades), C++17's `std::variant` offers a type-safe, visitor-based pattern that eliminates entire classes of bugs. I implemented both approaches for a simple UART protocol handler to compare code size, readability, and safety.

## The Core Concept

State machines are the backbone of embedded control logic — from protocol decoders to power management to button debouncing. The traditional approach uses an `enum class` for states and a `switch` statement for transitions. It works, but it has a fundamental flaw: the state variable and the transition logic are decoupled. Nothing prevents you from accidentally writing code that references an invalid state combination or forgets to handle a transition.

`std::variant` (C++17's type-safe union) flips this on its head. Instead of storing a state as an integer and switching on it, each state becomes its own type. The variant holds exactly one state at a time, and the compiler enforces that you handle every state when you visit it. For embedded systems where undefined behavior can brick hardware, this compile-time safety is gold.

The trade-off? `std::variant` FSMs tend to produce slightly larger code (due to vtable-like dispatch in `std::visit`) and require C++17 toolchain support. For resource-constrained MCUs (e.g., Cortex-M0 with 8KB flash), the `enum class` approach may still be the pragmatic choice.

## Key Commands / Configuration / Code

### Classic enum class FSM (UART byte stuffing example)

```cpp
#include <cstdint>
#include <cstddef>

enum class UartState : uint8_t {
    IDLE,
    RECEIVE_LENGTH,
    RECEIVE_DATA,
    CHECKSUM
};

struct UartDecoder {
    UartState state = UartState::IDLE;
    uint8_t buffer[64];
    size_t index = 0;
    uint8_t expected_length = 0;
    uint8_t checksum = 0;

    void process_byte(uint8_t byte) {
        switch (state) {
            case UartState::IDLE:
                if (byte == 0xAA) { // start byte
                    state = UartState::RECEIVE_LENGTH;
                    checksum = byte;
                }
                break;

            case UartState::RECEIVE_LENGTH:
                expected_length = byte;
                checksum ^= byte;
                index = 0;
                state = (expected_length > 0 && expected_length <= 64)
                    ? UartState::RECEIVE_DATA
                    : UartState::IDLE; // invalid length, reset
                break;

            case UartState::RECEIVE_DATA:
                buffer[index++] = byte;
                checksum ^= byte;
                if (index == expected_length) {
                    state = UartState::CHECKSUM;
                }
                break;

            case UartState::CHECKSUM:
                if (byte == checksum) {
                    // frame valid — handle it
                    on_frame_received(buffer, expected_length);
                }
                state = UartState::IDLE;
                break;
        }
    }

    void on_frame_received(const uint8_t* data, size_t len) {
        // application callback
    }
};
```

### Modern std::variant FSM (same logic, type-safe)

```cpp
#include <variant>
#include <cstdint>
#include <cstddef>

// Each state is its own struct — can hold per-state data
struct IdleState {
    uint8_t checksum = 0;
};

struct ReceiveLengthState {
    uint8_t checksum = 0;
};

struct ReceiveDataState {
    uint8_t buffer[64];
    size_t index = 0;
    uint8_t expected_length = 0;
    uint8_t checksum = 0;
};

struct ChecksumState {
    uint8_t buffer[64];
    size_t length = 0;
    uint8_t expected_checksum = 0;
};

// The variant holds exactly one state at a time
using UartState = std::variant<IdleState, ReceiveLengthState, 
                               ReceiveDataState, ChecksumState>;

struct UartDecoderVariant {
    UartState state = IdleState{};

    void process_byte(uint8_t byte) {
        // std::visit forces handling every state
        state = std::visit([byte](auto& s) -> UartState {
            using T = std::decay_t<decltype(s)>;

            if constexpr (std::is_same_v<T, IdleState>) {
                if (byte == 0xAA) {
                    return ReceiveLengthState{ .checksum = byte };
                }
                return IdleState{ .checksum = 0 }; // stay idle

            } else if constexpr (std::is_same_v<T, ReceiveLengthState>) {
                uint8_t len = byte;
                uint8_t new_checksum = s.checksum ^ byte;
                if (len > 0 && len <= 64) {
                    return ReceiveDataState{
                        .buffer = {},
                        .index = 0,
                        .expected_length = len,
                        .checksum = new_checksum
                    };
                }
                return IdleState{}; // invalid length

            } else if constexpr (std::is_same_v<T, ReceiveDataState>) {
                s.buffer[s.index++] = byte;
                s.checksum ^= byte;
                if (s.index == s.expected_length) {
                    return ChecksumState{
                        .buffer = {},
                        .length = s.expected_length,
                        .expected_checksum = s.checksum
                    };
                    // Note: need to copy buffer — real impl would use span
                }
                return std::move(s); // stay in data state

            } else if constexpr (std::is_same_v<T, ChecksumState>) {
                if (byte == s.expected_checksum) {
                    // frame valid — callback
                }
                return IdleState{};
            }
        }, state);
    }
};
```

## Common Pitfalls & Gotchas

1. **std::variant code bloat on small MCUs**: `std::visit` generates a dispatch table (similar to a vtable) for each visitor. On Cortex-M0 parts with 16KB flash, this can add 1-2KB of code. Always check the compiled size with `-Os` before committing. The `enum class` version typically compiles to a tight jump table.

2. **Copying state data in variant transitions**: In the `std::variant` example, transitioning from `ReceiveDataState` to `ChecksumState` requires copying the buffer. This is O(n) and can be a problem in ISRs. Consider using `std::unique_ptr` or a preallocated pool if the state data is large. The `enum class` version avoids this by keeping data in a single struct.

3. **Missing `constexpr` in state handlers**: The `std::visit` lambda must handle all types in the variant. If you add a new state type to the `using UartState = ...` alias and forget to add a handler, the compiler will error. This is a feature, not a bug — but it can be surprising when refactoring.

## Try It Yourself

1. **Extend the enum class FSM**: Add a `TIMEOUT` state that resets to `IDLE` if no byte is received within 100ms. Implement this using a hardware timer callback that sets a flag checked in `process_byte()`.

2. **Port to std::variant with constexpr**: Rewrite the `UartDecoderVariant` to use a `constexpr` visitor function instead of a lambda inside `process_byte()`. Measure the code size difference with `arm-none-eabi-size`.

3. **Add error counting**: Both FSMs should track invalid frames (bad checksum, invalid length, timeout). Add a `uint32_t error_count` that persists across state transitions. For the variant version, store this outside the variant (e.g., in the decoder struct).

## Next Up

Tomorrow: **Ring Buffer Implementation in Modern C++** — we'll build a lock-free, interrupt-safe ring buffer using `std::array` and atomics, then benchmark it against a traditional C implementation on a Cortex-M4 target.
