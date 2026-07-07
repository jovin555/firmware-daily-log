---
title: "Day 07: Dependency Injection in Embedded C: Decoupling Drivers from Logic"
date: 2026-07-07
tags: ["til", "hal-patterns", "dependency-injection"]
---

## What I Explored Today

Today I tackled one of the most practical decoupling techniques for embedded firmware: dependency injection (DI) in C. While DI is often associated with object-oriented languages, it maps cleanly to C through function pointers and opaque handles. The goal is to make your application logic completely unaware of which hardware driver it's talking to — enabling testability, portability, and hardware abstraction without a full RTOS or C++ compiler. I implemented a simple sensor polling module that can accept either a real I2C driver or a mock driver at runtime, all without changing a single line of application code.

## The Core Concept

Dependency injection means you don't let your module create its own dependencies. Instead, you pass them in — typically at initialization. In embedded C, this means your module receives pointers to the functions or structs it needs, rather than calling hardware-specific functions directly.

Why does this matter? Because the biggest pain in embedded firmware is hardware coupling. Your temperature sensor logic is full of `I2C_WriteRegister()` calls, your motor controller calls `GPIO_SetPin()` directly, and suddenly you can't test the logic without the actual hardware. With DI, your application module calls through a function pointer table. At startup, you inject either the real driver or a test stub. The module itself never knows the difference.

The pattern also enables hardware swapping without recompilation. If you switch from an internal ADC to an external I2C ADC, you write a new driver that conforms to the same interface, then inject it. The application logic stays untouched.

## Key Commands / Configuration / Code

Let's walk through a concrete example: a humidity sensor module that reads from either a real SHT30 sensor or a test mock.

First, define the interface as a struct of function pointers:

```c
// sensor_iface.h
typedef struct {
    int32_t (*init)(void* handle);
    int32_t (*read_humidity)(void* handle, float* humidity);
    int32_t (*read_temperature)(void* handle, float* temp);
} sensor_ops_t;
```

Now the application module that uses this interface. It never calls I2C directly:

```c
// humidity_monitor.c
#include "humidity_monitor.h"
#include <string.h>

typedef struct {
    const sensor_ops_t* ops;   // injected operations
    void*               hw;    // opaque hardware handle
    float               last_humidity;
} humidity_monitor_t;

// Constructor: dependency is injected here
humidity_monitor_t* humidity_monitor_create(const sensor_ops_t* ops, void* hw) {
    humidity_monitor_t* mon = malloc(sizeof(humidity_monitor_t));
    if (!mon) return NULL;
    mon->ops = ops;
    mon->hw  = hw;
    mon->last_humidity = 0.0f;
    return mon;
}

int32_t humidity_monitor_sample(humidity_monitor_t* mon) {
    // No idea if this is real hardware or a mock — doesn't matter
    return mon->ops->read_humidity(mon->hw, &mon->last_humidity);
}
```

Now implement the real driver conforming to the interface:

```c
// sht30_driver.c
#include "sensor_iface.h"
#include "i2c_hal.h"   // real I2C HAL

static int32_t sht30_init(void* handle) {
    i2c_handle_t* i2c = (i2c_handle_t*)handle;
    return i2c_write(i2c, 0x44, 0x2C06, 2);  // SHT30 measurement command
}

static int32_t sht30_read_humidity(void* handle, float* humidity) {
    // ... real I2C read and conversion
    return 0;
}

const sensor_ops_t sht30_ops = {
    .init            = sht30_init,
    .read_humidity   = sht30_read_humidity,
    .read_temperature = sht30_read_temp,  // defined similarly
};
```

And a mock for testing on your PC:

```c
// mock_sensor.c
#include "sensor_iface.h"

static int32_t mock_init(void* handle) {
    (void)handle;
    return 0;  // always succeeds
}

static int32_t mock_read_humidity(void* handle, float* humidity) {
    (void)handle;
    *humidity = 42.5f;  // fixed test value
    return 0;
}

const sensor_ops_t mock_sensor_ops = {
    .init            = mock_init,
    .read_humidity   = mock_read_humidity,
    .read_temperature = mock_read_temp,
};
```

Finally, wiring it all together in `main()`:

```c
// main.c
#include "humidity_monitor.h"
#include "sht30_driver.h"
#include "mock_sensor.h"

int main(void) {
    i2c_handle_t i2c_bus;
    i2c_init(&i2c_bus, 100000);  // 100 kHz

    // Inject real driver
    humidity_monitor_t* mon = humidity_monitor_create(&sht30_ops, &i2c_bus);

    // For unit tests, inject mock instead:
    // humidity_monitor_t* mon = humidity_monitor_create(&mock_sensor_ops, NULL);

    while (1) {
        humidity_monitor_sample(mon);
        delay_ms(1000);
    }
}
```

## Common Pitfalls & Gotchas

**1. Function pointer overhead in ISR context.** Each call through a function pointer adds an indirect branch and prevents inlining. In high-frequency ISRs (e.g., 100 kHz ADC sampling), this can cost microseconds. Solution: use DI for slow-path configuration and initialization, but keep hot paths direct. Or use link-time optimization (LTO) to let the compiler inline known targets.

**2. Forgetting const-correctness on the ops table.** If your ops struct is declared `const`, the compiler can place it in flash (ROM) on MCUs with Harvard architecture. Declare your interface tables as `const` and store them in flash. Otherwise, they'll consume precious RAM.

**3. Opaque handle type safety.** Using `void*` for the hardware handle loses all type information. A stray cast can corrupt memory. Mitigation: use a thin wrapper struct that contains a type tag, or use `_Generic` macros in C11 to add compile-time checks. For production code, I often define a base struct with a magic number field to validate handles at runtime.

## Try It Yourself

1. **Port an existing driver to DI.** Take a driver you've written that calls GPIO or SPI directly. Extract its public API into an ops struct. Refactor your application module to accept the ops struct at init. Verify it still works on hardware.

2. **Write a mock for PC testing.** Create a second implementation of your ops struct that returns fixed values or logs calls. Write a small test program (no hardware needed) that exercises your application logic with the mock injected. Compile with your native toolchain (gcc, not arm-none-eabi-gcc).

3. **Add a "null" driver.** Implement an ops struct where every function returns an error code. Inject it as a safety fallback when hardware initialization fails. This prevents your application from dereferencing NULL function pointers.

## Next Up

Tomorrow: **State Machines for Driver Design: Table-Driven vs Switch-Based**. We'll compare the classic switch-case state machine against table-driven approaches for complex driver protocols like SD card initialization or WiFi module command sequences. I'll show you when each pattern wins, and how to avoid the spaghetti state machine trap.
