---
title: "Day 04: Host-Based Testing: Running Firmware Tests on Linux"
date: 2026-06-16
tags: ["til", "hil-testing", "host-testing", "posix"]
---

## What I Explored Today

Today I dug into host-based testing for embedded firmware — specifically, compiling and running unit tests natively on Linux instead of cross-compiling for the target MCU. The goal is to catch logic bugs, boundary errors, and API misuse in seconds rather than minutes, without needing a debug probe or even a physical board. I set up a CMake project that builds both the firmware library and a native test executable using CTest and a lightweight test framework, and I validated that the same source files compile for both x86_64 and ARM Cortex-M targets.

## The Core Concept

Host-based testing means you take your embedded C/C++ source files — the ones that don't directly touch hardware registers or interrupt vectors — and compile them with your host compiler (gcc/clang) into a regular Linux process. The key insight: most of your firmware is *not* hardware-dependent. Sensor fusion algorithms, state machines, CRC calculations, protocol parsers, PID controllers — these are pure logic. By isolating them into a library that can be built for any platform, you unlock fast iteration cycles.

Why not just test on the target? Because every flash-debug-reset cycle costs 15–30 seconds of your life. Multiply that by 100 test cases and you've lost an hour. Host-based tests run in milliseconds. They also integrate naturally into CI pipelines — no need for a hardware farm or emulator. The trade-off is that you must mock or stub any hardware abstraction layer (HAL) calls, and you must ensure your build system can produce both host and target binaries from the same sources.

## Key Commands / Configuration / Code

### Project Structure
```
firmware/
├── CMakeLists.txt              # Top-level build
├── lib/
│   ├── CMakeLists.txt          # Library target (shared by host & target)
│   ├── crc16.c
│   ├── crc16.h
│   ├── state_machine.c
│   └── state_machine.h
├── test/
│   ├── CMakeLists.txt          # Test executable
│   ├── test_crc16.c
│   └── test_state_machine.c
└── target/
    ├── CMakeLists.txt          # Target firmware (cross-compiled)
    └── main.c
```

### Top-level CMakeLists.txt
```cmake
cmake_minimum_required(VERSION 3.20)
project(firmware LANGUAGES C)

# Host build: no cross-compiler, just native gcc
option(HOST_BUILD "Build for host testing" OFF)

if(HOST_BUILD)
    set(CMAKE_C_STANDARD 11)
    set(CMAKE_C_STANDARD_REQUIRED ON)
    add_subdirectory(lib)
    add_subdirectory(test)
else()
    # Target build: cross-compiler toolchain file
    set(CMAKE_TOOLCHAIN_FILE "${CMAKE_SOURCE_DIR}/toolchain-arm-none-eabi.cmake")
    add_subdirectory(lib)
    add_subdirectory(target)
endif()
```

### Library CMakeLists.txt (lib/)
```cmake
add_library(firmware_core STATIC
    crc16.c
    state_machine.c
)

# Public headers for both host and target
target_include_directories(firmware_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR})
```

### Test CMakeLists.txt (test/)
```cmake
# Use Check framework (tiny, no external deps)
find_package(Check REQUIRED)

add_executable(test_firmware
    test_crc16.c
    test_state_machine.c
)

target_link_libraries(test_firmware PRIVATE firmware_core Check::Check)

# Register with CTest
include(CTest)
add_test(NAME firmware_tests COMMAND test_firmware)
```

### Example test (test_crc16.c)
```c
#include <check.h>
#include "crc16.h"  // Same header used on target

START_TEST(test_crc16_known_values)
{
    uint8_t data[] = {0x01, 0x02, 0x03, 0x04};
    uint16_t crc = crc16_calculate(data, sizeof(data));
    // Known CRC-16-IBM result for this input
    ck_assert_uint_eq(crc, 0x3D4A);
}
END_TEST

START_TEST(test_crc16_empty_input)
{
    uint16_t crc = crc16_calculate(NULL, 0);
    ck_assert_uint_eq(crc, 0x0000);  // Or 0xFFFF, depending on init
}
END_TEST

Suite* crc16_suite(void)
{
    Suite *s = suite_create("CRC16");
    TCase *tc = tcase_create("Core");
    tcase_add_test(tc, test_crc16_known_values);
    tcase_add_test(tc, test_crc16_empty_input);
    suite_add_tcase(s, tc);
    return s;
}
```

### Build and run
```bash
# Configure for host testing
cmake -B build_host -DHOST_BUILD=ON

# Build and run tests
cmake --build build_host
cd build_host && ctest --output-on-failure

# Output: 100% tests passed, 0.002 sec
```

## Common Pitfalls & Gotchas

1. **Endianness surprises.** Your x86 host is little-endian; your ARM target might be too, but many network protocols and sensor data are big-endian. If your CRC or protocol parser assumes host byte order, tests pass on Linux but fail on target. Always write endian-agnostic code (e.g., use `htons`, `ntohl`, or explicit byte shuffling).

2. **Compiler-specific extensions.** You might use `__attribute__((packed))` for structs on GCC/ARM, which also works on host GCC. But if you use CMSIS intrinsics like `__LDREXW` or `__WFE`, those won't compile on x86. Isolate such code behind `#ifdef __ARM_ARCH` guards or move them into a hardware abstraction layer that you stub during host tests.

3. **Stack size assumptions.** On an MCU, your stack might be 4 KB. On Linux, it's 8 MB. A recursive function that works fine in host tests will blow the stack on target. Add a `-Wl,--stack,4096` linker flag during host builds, or better, use static analysis to detect deep recursion.

## Try It Yourself

1. **Port a CRC module.** Take any CRC-32 or CRC-16 implementation from your current firmware, extract it into a standalone library, and write 5 test cases using the Check framework. Verify against known online CRC calculators.

2. **Mock a HAL function.** Create a simple `hal_gpio_write(pin, state)` that toggles a global variable instead of a real GPIO. Write a state machine test that verifies the correct sequence of GPIO writes for a given input sequence.

3. **Add a memory boundary test.** Write a test that passes a buffer of exactly the minimum size to a parsing function, then one byte less. Verify the function returns an error code instead of buffer-overflowing.

## Next Up

Tomorrow I'll explore **pytest-embedded**, a Python test runner that wraps your firmware binaries and provides fixture-based hardware control, serial monitoring, and automatic flashing — bridging the gap between host-based unit tests and full HIL validation.
