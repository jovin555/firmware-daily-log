---
title: "Day 15: Software Integration & Integration Testing"
date: 2026-06-27
tags: ["til", "iec62304", "integration", "build"]
---

## What I Explored Today

Today I dug into the software integration and integration testing requirements under IEC 62304, specifically Clause 5.6 and 6.2. The standard mandates that software units be integrated according to an integration plan, and that integration tests verify the interactions between those units. I focused on the practical mechanics: how to structure a build system to enforce integration order, how to write integration tests that actually catch interface defects, and how to trace those tests back to the software architecture. The key insight is that integration testing isn't just "bigger unit tests"—it's a distinct verification activity targeting the seams between components.

## The Core Concept

Integration testing exists because unit tests lie. A unit test for a temperature sensor driver might pass in isolation, but when that driver is integrated with a PID controller that expects a different data format, the system fails. IEC 62304 recognizes this by requiring integration tests to cover all interfaces between software units, including data flow, control flow, and timing.

The "why" is rooted in risk: interface defects are among the most expensive to fix late in development. The standard's integration testing requirements (Clause 6.2.2) demand that tests be derived from the software architecture, not just the implementation. This means your integration test plan must map to the component interaction diagram in your design document. If you have a layered architecture, you integrate bottom-up. If you have a publish-subscribe architecture, you integrate by topic or channel.

The practical approach I use is to define integration levels that correspond to architectural layers. Each level has a build target and a test suite. The build system enforces that you cannot integrate level N+1 until level N passes. This creates a gating mechanism that prevents the "big bang" integration disaster where everything breaks at once and nobody knows why.

## Key Commands / Configuration / Code

Here's a CMake-based integration build system that enforces layered integration. This is for a medical device with three layers: HAL (Hardware Abstraction), Middleware, and Application.

```cmake
# CMakeLists.txt — Integration build with gating
cmake_minimum_required(VERSION 3.20)
project(ventilator_controller)

# Integration test targets — each level depends on previous passing
add_custom_target(integration_level_1
    COMMAND ${CMAKE_CTEST_COMMAND} -R "hal_integration" --output-on-failure
    COMMENT "Running HAL integration tests"
)

add_custom_target(integration_level_2
    COMMAND ${CMAKE_CTEST_COMMAND} -R "middleware_integration" --output-on-failure
    COMMENT "Running Middleware integration tests"
)
add_dependencies(integration_level_2 integration_level_1)  # Gate: Level 1 must pass

add_custom_target(integration_level_3
    COMMAND ${CMAKE_CTEST_COMMAND} -R "app_integration" --output-on-failure
    COMMENT "Running Application integration tests"
)
add_dependencies(integration_level_3 integration_level_2)  # Gate: Level 2 must pass

# Build the integration test executables
add_executable(test_hal_integration
    test/hal/test_sensor_integration.cpp
    src/hal/sensor_driver.c
    src/hal/adc_wrapper.c
)
target_link_libraries(test_hal_integration PRIVATE unity)  # Unity test framework
add_test(NAME hal_integration COMMAND test_hal_integration)
```

Now, an actual integration test using the Unity test framework. This tests the interface between the ADC wrapper and the sensor driver:

```c
// test/hal/test_sensor_integration.c
#include "unity.h"
#include "sensor_driver.h"
#include "adc_wrapper.h"

// Stub for the ADC — we inject a known voltage
static uint16_t stub_adc_value = 0;

void setUp(void) {
    adc_init();
    sensor_init();
    stub_adc_value = 0;
}

void test_sensor_reads_adc_and_converts_to_millivolts(void) {
    // Arrange: inject 2048 ADC counts (assuming 12-bit ADC, 3.3V ref)
    // 2048 counts = 1.65V = 1650 mV
    stub_adc_value = 2048;
    adc_set_stub_value(&stub_adc_value);  // Inject via test hook

    // Act: read sensor
    uint32_t mv = sensor_read_millivolts();

    // Assert: 2048 * 3300 / 4096 = 1650
    TEST_ASSERT_EQUAL_UINT32(1650, mv);
}

void test_sensor_handles_adc_overflow_gracefully(void) {
    // Arrange: ADC returns 4095 (max value)
    stub_adc_value = 4095;
    adc_set_stub_value(&stub_adc_value);

    // Act
    uint32_t mv = sensor_read_millivolts();

    // Assert: should saturate at 3300 mV, not wrap
    TEST_ASSERT_EQUAL_UINT32(3300, mv);
}

int main(void) {
    UNITY_BEGIN();
    RUN_TEST(test_sensor_reads_adc_and_converts_to_millivolts);
    RUN_TEST(test_sensor_handles_adc_overflow_gracefully);
    return UNITY_END();
}
```

The critical detail here is `adc_set_stub_value()` — that's a test hook compiled only in test builds. In production, the ADC reads from hardware. In test, we inject values. This is how you test the *interface* without needing the actual hardware.

## Common Pitfalls & Gotchas

**1. Treating integration tests like large unit tests.** I've seen teams write integration tests that mock everything except the unit under test. That's just a unit test with extra steps. Real integration tests should use as few mocks as possible. The goal is to test the actual interaction between real (or near-real) components. For the ADC example above, the stub is necessary because we can't control hardware in CI, but the sensor driver and ADC wrapper are both real code.

**2. Forgetting to test error propagation.** Integration tests often only test the happy path. IEC 62304 requires that you test how errors propagate across interfaces. What happens when the middleware gets a corrupted packet from the communication layer? Does it return an error code that the application checks? Write a test that injects a CRC failure and verifies the application enters a safe state.

**3. No build gating.** Without enforcing integration order in the build system, developers will merge code that breaks the interface contract. The CMake `add_dependencies()` call above is not optional — it's the mechanism that prevents level 3 from building if level 2 tests fail. In CI, this means your pipeline should fail fast: if `integration_level_1` fails, don't even attempt `integration_level_2`.

## Try It Yourself

1. **Define your integration levels.** Take your current software architecture diagram and identify 3-4 layers or subsystems. Write a short integration plan that specifies the order of integration (e.g., HAL → Middleware → Application → Safety Monitor). Document what interfaces are tested at each level.

2. **Write one integration test for a real interface.** Pick two components that communicate in your system. Write a test that uses a test hook (like the ADC stub above) to inject data at the boundary of one component and verify the output of the other. Run it and confirm it passes.

3. **Add build gating.** If you use CMake, add `add_dependencies()` to enforce your integration order. If you use another build system, add a CI step that runs lower-level integration tests before higher-level ones. Verify that a failing lower-level test blocks the higher-level build.

## Next Up

Tomorrow: Software System Testing: Plans, Cases & Reports — how to take your integrated software and validate it against the system requirements, including traceability matrices and acceptance criteria that satisfy the auditors.
