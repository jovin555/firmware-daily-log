---
title: "Day 08: std::variant & std::optional for Error Handling"
date: 2026-06-22
tags: ["til", "cpp-embedded", "variant", "optional", "error"]
---

## What I Explored Today

Today I dug into two C++17 features that have fundamentally changed how I handle uncertain states in embedded firmware: `std::variant` and `std::optional`. These aren't just syntactic sugar—they replace error-prone patterns like sentinel values, out-parameters, and error code enums that have caused countless bugs in my production code. I focused specifically on how they interact with the resource constraints and deterministic requirements of embedded systems.

## The Core Concept

Embedded engineers face a unique tension: we need to handle failure modes (sensor read errors, communication timeouts, invalid configuration) without the luxury of exceptions or dynamic memory allocation. Traditional approaches are brittle. Returning `-1` for an error? That assumes `-1` is never a valid reading. Using an out-parameter for the value and a return for the error code? That doubles the cognitive load and makes composition impossible.

`std::optional<T>` says: "I either have a valid `T`, or I have nothing." It's a tagged union that the compiler can optimize to a single `bool` plus the value storage—zero overhead when the value fits in a register.

`std::variant<T, E>` says: "I am either a `T` (success) or an `E` (error)." This is a type-safe union. No reinterpret_cast, no manual discriminant tracking. The compiler enforces that you check which alternative is active before accessing it.

Together, they let us write functions that are self-documenting, composable, and impossible to misuse at compile time. The key insight: **the type system becomes the error handling documentation**.

## Key Commands / Configuration / Code

### std::optional: The "Maybe" Pattern

```cpp
#include <optional>
#include <cstdint>

// Returns std::nullopt if sensor communication fails
std::optional<uint16_t> read_temperature_sensor() {
    if (!sensor_is_ready()) {
        return std::nullopt;  // No value
    }
    return sensor_read_register(0x42);  // Valid uint16_t
}

// Usage in a control loop
void control_loop() {
    auto temp = read_temperature_sensor();
    
    // Safe access with value_or() — no crash if nullopt
    uint16_t current_temp = temp.value_or(25);  // Default to 25°C
    
    // Or explicit check
    if (temp.has_value()) {
        process_temperature(temp.value());  // Guaranteed valid
    }
}
```

### std::variant: The "Either" Pattern

```cpp
#include <variant>
#include <cstdint>

// Error types — zero-overhead enum
enum class SensorError : uint8_t {
    None = 0,
    CommunicationTimeout,
    CRC_Mismatch,
    PowerSupplyFault
};

// Return type: either a valid reading or a specific error
using SensorResult = std::variant<uint16_t, SensorError>;

SensorResult read_pressure_sensor() {
    if (!i2c_bus_acquire()) {
        return SensorError::CommunicationTimeout;
    }
    
    uint16_t raw = i2c_read_16bit(0x44);
    if (!crc_check(raw)) {
        return SensorError::CRC_Mismatch;
    }
    
    return raw;  // Implicitly constructs variant with uint16_t
}

// Usage — compile-time checked access
void handle_sensor() {
    auto result = read_pressure_sensor();
    
    // std::visit — the safe dispatcher
    std::visit([](auto&& arg) {
        using T = std::decay_t<decltype(arg)>;
        if constexpr (std::is_same_v<T, uint16_t>) {
            // Compiler knows this is the value branch
            log_value(arg);
        } else if constexpr (std::is_same_v<T, SensorError>) {
            // Compiler knows this is the error branch
            log_error(arg);
        }
    }, result);
}
```

### Embedded-Friendly Pattern: Result Type

```cpp
template<typename T, typename E>
class Result {
    std::variant<T, E> data;
public:
    explicit Result(T&& val) : data(std::forward<T>(val)) {}
    explicit Result(E&& err) : data(std::forward<E>(err)) {}
    
    bool is_ok() const { return std::holds_alternative<T>(data); }
    T& value() { return std::get<T>(data); }
    E& error() { return std::get<E>(data); }
};

// Usage — no dynamic allocation, no exceptions
Result<uint32_t, const char*> read_adc_channel(int channel) {
    if (channel > 7) return Result<uint32_t, const char*>("Invalid channel");
    return Result<uint32_t, const char*>(adc_read(channel));
}
```

## Common Pitfalls & Gotchas

1. **std::variant default construction** — `std::variant<T, E> v;` default-constructs the *first* alternative. If `T` is a primitive like `int`, it's zero-initialized. This can mask bugs where you forget to assign a meaningful value. Always explicitly initialize or use a dedicated "uninitialized" type as the first alternative.

2. **std::optional<bool> is a trap** — `std::optional<bool>` has three states: `nullopt`, `true`, `false`. But `if (opt)` checks *has_value*, not the boolean value. Use `opt.value_or(false)` for clarity, or prefer `std::optional<int>` with 0/1 semantics.

3. **Variant size on stack** — `std::variant` is always at least as large as its largest alternative. If you store a 256-byte struct alongside a `uint8_t`, every variant instance costs 256+ bytes. Profile your stack usage. Consider using `std::unique_ptr` for large alternatives only if your platform supports dynamic allocation (many embedded RTOS do, but bare-metal often doesn't).

4. **std::get throws on wrong access** — `std::get<T>(variant)` throws `std::bad_variant_access` if the wrong alternative is active. In embedded systems without exception support, this calls `std::terminate()`. Always use `std::get_if<T>(&variant)` which returns a null pointer on mismatch, or `std::visit` which is compile-time safe.

## Try It Yourself

1. **Refactor a sentinel-value function**: Take a function that returns `int` with `-1` for error (e.g., a UART read that returns byte or -1 on timeout). Rewrite it to return `std::optional<uint8_t>`. Measure the code size difference with `-Os` on your target compiler.

2. **Build a multi-error variant**: Create a `std::variant<SensorReading, I2CError, TimeoutError, CalibrationError>` for a sensor driver. Implement `std::visit` to log each error type differently. Ensure the variant fits in 32 bytes or less.

3. **Compose with monadic operations** (C++23): If your toolchain supports it, chain `std::optional` operations: `read_sensor().and_then(validate).or_else(fallback)`. If not, implement `and_then` and `or_else` as free functions for your custom `Result` type.

## Next Up

Tomorrow, we'll look at **Lambda Expressions & Callbacks in Firmware** — how to use stateless and capturing lambdas as function pointers for ISRs, timer callbacks, and state machines without dynamic allocation. We'll cover the `+` operator trick for lambda-to-function-pointer conversion and when `mutable` lambdas actually make sense in embedded contexts.
