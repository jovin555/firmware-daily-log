---
title: "Day 23: Host-Based Testing: Running Firmware Tests on Linux"
date: 2026-07-05
tags: ["til", "hil-testing", "host-testing", "posix"]
---

## What I Explored Today

Today I dug into host-based testing for embedded firmware — compiling and running unit tests natively on a Linux host rather than cross-compiling for the target MCU. The goal was to get a real-time scheduler module (written for ARM Cortex-M) executing on my x86 workstation, with full GDB debugging and Valgrind memory analysis. After fighting with compiler intrinsics and linker scripts for a few hours, I had a working test harness that runs 47 unit tests in under 200ms, catching a subtle buffer overflow that would have been a nightmare to find on hardware.

## The Core Concept

Host-based testing means you compile your embedded C/C++ code with the host's native toolchain (gcc/clang) instead of the cross-compiler (arm-none-eabi-gcc). The key insight: most firmware business logic — state machines, protocol parsers, control algorithms, scheduler queues — is pure C code that doesn't depend on hardware registers or interrupt vectors. By abstracting hardware dependencies behind thin HAL layers or weak symbols, you can test this logic at full native speed with all the debugging tools Linux provides.

The "why" is simple: iteration speed. A typical embedded build-test-flash cycle takes 30-60 seconds minimum. Host-based tests run in milliseconds. You can run them on every git push, in CI pipelines, and with memory sanitizers that don't exist on embedded targets. The trade-off is you're not testing the actual hardware interaction — but that's what HIL testing is for. Host-based testing fills the gap between "I wrote this code" and "I'm ready to flash it."

## Key Commands / Configuration / Code

### The Build System Trick (CMake)

The most common approach is a CMake option that swaps the toolchain:

```cmake
# CMakeLists.txt
option(HOST_TEST "Build for host-based testing" OFF)

if(HOST_TEST)
    set(CMAKE_C_COMPILER gcc)
    set(CMAKE_CXX_COMPILER g++)
    add_compile_definitions(HOST_TEST=1)
    # Mock the hardware abstraction layer
    add_subdirectory(mocks)
else()
    set(CMAKE_C_COMPILER arm-none-eabi-gcc)
    set(CMAKE_CXX_COMPILER arm-none-eabi-g++)
    add_compile_definitions(STM32F4XX)
endif()
```

### Mocking Hardware Registers

For a UART driver, you replace register writes with function calls:

```c
// uart_driver.c — production code
#ifdef HOST_TEST
    // Weak symbols get overridden by test mocks
    __attribute__((weak)) void uart_write_reg(uint32_t reg, uint32_t val) {
        // No-op on host
    }
#else
    #define uart_write_reg(reg, val) (*(volatile uint32_t*)(reg) = (val))
#endif

void uart_send_byte(char c) {
    while(!(UART_SR & TX_READY));  // This won't work on host
    uart_write_reg(UART_DR, c);
}
```

Better approach — use a function pointer table:

```c
// hal_uart.h
typedef struct {
    void (*send_byte)(char c);
    char (*receive_byte)(void);
    int (*is_tx_ready)(void);
} uart_hal_t;

extern uart_hal_t uart_hal;  // Set by init or test setup
```

### Running Tests with Unity + Valgrind

```bash
# Build with host toolchain
mkdir build_host && cd build_host
cmake .. -DHOST_TEST=ON -DCMAKE_BUILD_TYPE=Debug
make -j$(nproc)

# Run tests with memory checking
valgrind --leak-check=full --error-exitcode=1 ./test_scheduler

# Run with address sanitizer (no Valgrind overhead)
cmake .. -DHOST_TEST=ON -DCMAKE_BUILD_TYPE=Debug -DSANITIZE=ON
# In CMakeLists.txt:
# target_compile_options(test_scheduler PRIVATE -fsanitize=address -fno-omit-frame-pointer)
# target_link_libraries(test_scheduler PRIVATE -fsanitize=address)
```

### Example Test (Unity Framework)

```c
// test_scheduler.c
#include "unity.h"
#include "scheduler.h"

// Mock timer — no hardware timer needed
static uint32_t mock_ticks = 0;
uint32_t hal_get_tick(void) { return mock_ticks; }

void setUp(void) {
    scheduler_init();
    mock_ticks = 0;
}

void test_task_runs_after_delay(void) {
    volatile bool task_ran = false;
    scheduler_add_task(10, 0, (void (*)(void*))&task_ran, NULL);
    
    mock_ticks = 9;
    scheduler_tick();  // Should not run yet
    TEST_ASSERT_FALSE(task_ran);
    
    mock_ticks = 10;
    scheduler_tick();  // Should run now
    TEST_ASSERT_TRUE(task_ran);
}

int main(void) {
    UNITY_BEGIN();
    RUN_TEST(test_task_runs_after_delay);
    return UNITY_END();
}
```

## Common Pitfalls & Gotchas

### 1. Compiler Intrinsics and Builtins
ARM Cortex-M has specific intrinsics like `__disable_irq()`, `__WFI()`, or `__SVC(0)`. These don't exist on x86. Solution: wrap them in macros that expand to nothing on host, or provide stub implementations. I wasted an hour because `__builtin_arm_wsb()` silently compiled to a no-op on gcc x86 but the code logic depended on the memory barrier.

### 2. Alignment and Packing Differences
ARM allows unaligned access (with performance penalty), x86 generally doesn't. If your firmware uses `__attribute__((packed))` on structs, the memory layout is identical, but accessing misaligned members on x86 can cause SIGBUS. Always test with `-fsanitize=alignment` or use `memcpy()` for field access in portable code.

### 3. Linker Scripts and Memory Sections
Your firmware likely has custom linker sections (`.isr_vector`, `.ccmram`). The host linker won't know about them. Either strip them with preprocessor guards, or provide a minimal host linker script that just places everything in `.text`/`.data`/`.bss`. I've seen teams accidentally include the full STM32 linker script in host builds — the linker silently ignores unknown sections, but variables in custom sections end up with wrong addresses.

## Try It Yourself

1. **Port a simple state machine to host**: Take a button debounce or LED pattern module from your firmware. Replace all `HAL_GPIO_*` calls with mock functions that log calls to a buffer. Write 3 unit tests that verify state transitions.

2. **Run with AddressSanitizer**: Compile your scheduler or queue module with `-fsanitize=address -g`. Intentionally introduce a buffer overflow (e.g., write past array bounds) and watch ASan catch it with a precise stack trace.

3. **Add Valgrind to your CI**: Create a GitHub Actions workflow that builds with `-DHOST_TEST=ON` and runs `valgrind --leak-check=full --error-exitcode=1 ./test_suite`. Make it a required check before merging.

## Next Up

Tomorrow I'm diving into **pytest-embedded**, Espressif's Python test runner that wraps Unity/Catch2 tests and adds serial port interaction, flash automation, and DUT lifecycle management. It's the bridge between host-based unit tests and full HIL — and it works with any chip, not just ESP32.
