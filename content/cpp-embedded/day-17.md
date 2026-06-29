---
title: "Day 17: AUTOSAR C++14: Subset for Safety-Critical Systems"
date: 2026-06-29
tags: ["til", "cpp-embedded", "autosar", "cpp14", "safety"]
---

## What I Explored Today

Today I dug into AUTOSAR C++14, the coding standard that defines a safe subset of C++14 for automotive safety-critical systems (ASIL B/C/D). Unlike MISRA C++ 2008 (which is based on C++03), AUTOSAR C++14 aligns with modern C++ while still enforcing strict rules to prevent undefined behavior, dynamic memory hazards, and runtime failures. I focused on the practical "why" behind the rules and how to enforce them with static analysis tools like clang-tidy and cppcheck.

## The Core Concept

AUTOSAR C++14 isn't just a list of "don't do this" rules — it's a philosophy: *use the type system to eliminate entire classes of bugs at compile time*. The standard explicitly bans dynamic memory allocation (`new`/`delete`, `malloc`/`free`) in production code, mandates RAII for resource management, and requires that all virtual functions be declared `final` or have a `virtual` destructor. Why? Because in a safety-critical ECU, a heap fragmentation crash or a vtable corruption is a recall event.

The key insight: AUTOSAR C++14 forces you to write code that is *provably correct* through static analysis. It replaces runtime checks (like `dynamic_cast`) with compile-time alternatives (`static_cast` with bounds checking, or `std::variant`). It also bans recursion (stack overflow risk) and requires that all loops have a bounded iteration count.

## Key Commands / Configuration / Code

### 1. Enabling AUTOSAR checks with clang-tidy

Create a `.clang-tidy` file in your project root:

```yaml
# .clang-tidy for AUTOSAR C++14 compliance
Checks: >
  -*,
  autosar-*,
  cppcoreguidelines-*,
  misc-*,
  performance-*,
  readability-*
CheckOptions:
  - key:   autosar.A5-1-1.AllowLiteralSuffix
    value: '0'  # Ban user-defined literals
  - key:   autosar.M7-3-1.AllowGlobalOperators
    value: '0'  # Ban global operator new/delete
WarningsAsErrors: '*'
```

Run it on your source:
```bash
clang-tidy --config-file=.clang-tidy src/main.cpp -- -std=c++14 -Iinclude
```

### 2. Banned: `new`/`delete` — use `std::array` or static pools

```cpp
// VIOLATION: AUTOSAR A18-5-2 (dynamic memory allocation)
auto* buffer = new uint8_t[1024];  // Banned in safety-critical code

// COMPLIANT: static allocation with std::array
#include <array>
std::array<uint8_t, 1024> buffer;  // Stack-allocated, deterministic

// For variable-size needs: use a static pool
template<typename T, size_t N>
class StaticPool {
    std::array<T, N> storage{};
    std::bitset<N> used{};
public:
    T* allocate() {
        for (size_t i = 0; i < N; ++i) {
            if (!used[i]) {
                used.set(i);
                return &storage[i];
            }
        }
        return nullptr;  // Handle exhaustion
    }
    void deallocate(T* ptr) {
        size_t idx = ptr - storage.data();
        used.reset(idx);
    }
};
```

### 3. Banned: `dynamic_cast` — use `std::variant` or CRTP

```cpp
// VIOLATION: AUTOSAR A5-2-3 (dynamic_cast on polymorphic types)
if (auto* derived = dynamic_cast<Derived*>(base)) {  // Banned
    derived->specificMethod();
}

// COMPLIANT: std::variant with visitor pattern
#include <variant>
using Command = std::variant<StartCmd, StopCmd, ResetCmd>;

struct CommandHandler {
    void operator()(const StartCmd&) { /* ... */ }
    void operator()(const StopCmd&)  { /* ... */ }
    void operator()(const ResetCmd&) { /* ... */ }
};

void handle(Command& cmd) {
    std::visit(CommandHandler{}, cmd);  // Compile-time dispatch
}
```

### 4. Mandatory: `final` on leaf classes

```cpp
// AUTOSAR A10-3-1: All virtual functions must be final or have virtual destructor
class SensorBase {
public:
    virtual ~SensorBase() = default;  // OK: virtual destructor
    virtual float read() = 0;
};

class TemperatureSensor final : public SensorBase {  // final: no further derivation
public:
    float read() override { return 25.0f; }
};

// VIOLATION: missing final, missing virtual destructor
class BadSensor : public SensorBase {  // AUTOSAR violation
    float read() override { return 0.0f; }
    // ~BadSensor() not virtual — UB on delete through base pointer
};
```

## Common Pitfalls & Gotchas

1. **`std::function` is banned** — AUTOSAR A18-5-2 prohibits type-erased call wrappers because they may allocate internally. Use function pointers or `std::reference_wrapper` with concrete lambdas instead. I once spent a day refactoring a callback system to use `template<typename F> void registerHandler(F&& f)` — it's verbose but deterministic.

2. **`constexpr` is not a free pass** — Just because a function is `constexpr` doesn't mean it's AUTOSAR-compliant. Rule A5-1-1 bans `constexpr` functions that contain loops with non-constant bounds. Always check: does this function have a deterministic upper bound on iterations? If not, it's a violation.

3. **`reinterpret_cast` is banned except for hardware access** — AUTOSAR A5-2-4 allows `reinterpret_cast` only when casting to/from `uintptr_t` for memory-mapped registers. Many engineers use it for serialization (e.g., casting a struct to `uint8_t*`). That's a violation. Use `std::bit_cast` (C++20) or explicit `memcpy` into a `uint8_t` array.

## Try It Yourself

1. **Audit your codebase**: Run `clang-tidy` with the AUTOSAR checks on a single source file. Count how many violations of A18-5-2 (dynamic memory) and A5-2-3 (dynamic_cast) you find. Refactor one of them to use `std::array` or `std::variant`.

2. **Write a static pool allocator**: Implement a `StaticPool<T, N>` that supports `allocate()` and `deallocate()` without using `new`/`delete`. Add a `constexpr` test that verifies all allocations succeed for `N` elements.

3. **Convert a polymorphic hierarchy to `std::variant`**: Take a small class hierarchy (e.g., `Command` base with `Start`, `Stop`, `Reset` derived classes) and replace it with a `std::variant` + visitor. Measure the code size difference (embedded compilers often inline variant dispatch better than vtable calls).

## Next Up

Tomorrow: **Undefined Behavior: UBSan & Catching UB in Firmware** — we'll run UndefinedBehaviorSanitizer on a bare-metal ARM target to catch signed overflow, misaligned access, and null pointer dereferences that AUTOSAR rules alone can't prevent.
