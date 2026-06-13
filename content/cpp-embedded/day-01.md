---
title: "Day 01: Why C++ in Embedded? Myths, Tradeoffs & Modern Approach"
date: 2026-06-13
tags: ["til", "cpp-embedded", "cpp", "embedded", "tradeoffs"]
---

## What I Explored Today

I spent the day dissecting why C++ remains a polarizing choice in embedded systems—and whether the skepticism is still warranted. After reviewing real-world firmware bases (from automotive ECUs to IoT sensor nodes), I concluded that the real question isn't "C or C++?" but rather "Which subset of C++ is appropriate for my resource constraints?" Today's deep dive covered the performance myth, the hidden costs of exceptions and RTTI, and how modern C++ (C++17/20) actually gives us better tools for zero-overhead abstraction than traditional C.

## The Core Concept

The embedded world has a long memory. Many engineers still associate C++ with the bloat of early compilers, virtual dispatch overhead, and unpredictable heap allocations. But the reality is more nuanced. C++ offers a "pay only for what you use" contract: language features you don't use cost you nothing at runtime. The key is understanding which features are free and which carry hidden costs.

**The real tradeoff is between abstraction and control.** C gives you total visibility into every memory access and function call. C++ gives you templates, constexpr, and RAII—tools that shift complexity from runtime to compile time. For embedded, this means you can write generic drivers without function pointer overhead, compute lookup tables at compile time, and guarantee resource cleanup without relying on a garbage collector.

The myth that C++ is "too slow" for embedded comes from misuse of dynamic dispatch (`virtual`), exceptions, and runtime type identification (RTTI). Disable those (they're off by default in many embedded toolchains), and you're left with a language that compiles to the same machine code as C—but with better type safety and code organization.

## Key Commands / Configuration / Code

### Disabling the Expensive Features

For GCC ARM embedded, your `CMakeLists.txt` or Makefile should include:

```cmake
# Disable exceptions, RTTI, and threading overhead
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fno-exceptions -fno-rtti -nostdlib++")
# Optimize for size, no unwind tables
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -Os -fno-unwind-tables -fno-asynchronous-unwind-tables")
```

### Zero-Cost Abstraction: Template vs. Function Pointer

Compare a traditional C callback pattern with a C++ template:

```cpp
// C-style: function pointer, runtime indirection
void timer_set_callback(void (*cb)(void*), void* arg);

// C++ template: compile-time resolution, zero overhead
template<typename Callable>
void timer_set_callback(Callable&& cb) {
    // cb is inlined at call site, no pointer dereference
    register_callback(static_cast<void(*)()>(cb));
}
```

The template version generates identical assembly to a direct function call—no pointer chasing, no indirect branch.

### Constexpr for Compile-Time Computation

```cpp
// Compute CRC table at compile time, not at boot
consteval uint32_t crc32_table() {
    uint32_t table[256] = {};
    for (uint32_t i = 0; i < 256; ++i) {
        uint32_t crc = i;
        for (int j = 0; j < 8; ++j) {
            crc = (crc >> 1) ^ (crc & 1 ? 0xEDB88320 : 0);
        }
        table[i] = crc;
    }
    return table[0]; // or store entire table in flash
}
// Usage: zero runtime cost, table lives in .rodata
static constexpr uint32_t crc_init = crc32_table();
```

### Minimal C++17 Startup (No Standard Library)

```cpp
// minimal.cpp — no std::vector, no new/delete
extern "C" void Reset_Handler() {
    // Copy .data, zero .bss (same as C)
    __data_start = ...;  // linker symbols
    
    // Call global constructors for static objects
    __libc_init_array();
    
    // Enter main — never returns
    main();
    
    while(1);
}
```

## Common Pitfalls & Gotchas

1. **Virtual functions in ISRs** — A virtual call inside an interrupt handler can cause non-deterministic latency because the vtable lookup may miss the cache. Worse, if the vtable pointer is corrupted (e.g., by stack overflow), you get a hard fault. Rule: never use `virtual` in interrupt context; use function pointers or templates.

2. **Static initialization order fiasco** — C++ runs constructors for global/static objects before `main()`. If one static object's constructor depends on another (e.g., a UART object that uses a GPIO object), the order is undefined across translation units. Fix: use `constexpr` where possible, or lazy initialization with `std::optional` (C++17) instead of globals.

3. **Implicit heap allocations** — `std::string`, `std::vector`, and `std::map` allocate on the heap by default. In a bare-metal system with no heap, these will crash at runtime. Always use custom allocators or fixed-size containers (e.g., `etl::string`, `std::array`). Enable `-Wzero-as-null-pointer-constant` to catch accidental heap usage.

## Try It Yourself

1. **Audit your current project** — Search for `virtual`, `throw`, `dynamic_cast`, and `std::string` in your firmware. Count how many are actually necessary vs. convenience. Disable exceptions and RTTI in your build system; does it still compile?

2. **Replace a C callback with a template** — Find a timer or interrupt registration that uses `void (*cb)(void*)`. Rewrite it as a template function. Compare the generated assembly (use `objdump -d` or Compiler Explorer) — are the instruction counts identical?

3. **Move a runtime calculation to compile time** — Identify a lookup table (CRC, sine, filter coefficients) computed at boot. Rewrite it as `consteval` (C++20) or `constexpr` (C++11/14). Verify the table ends up in `.rodata` via `arm-none-eabi-objdump -s`.

## Next Up

Tomorrow we tackle **RAII: Resource Acquisition Is Initialization for Hardware** — how to make GPIO pins, SPI transactions, and DMA buffers self-cleaning using constructor/destructor pairs. No more forgetting to release a lock or close a peripheral.
