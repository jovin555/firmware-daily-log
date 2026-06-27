---
title: "Day 15: C++ in Zephyr: Enabling & Writing C++ Drivers"
date: 2026-06-27
tags: ["til", "cpp-embedded", "zephyr", "cpp", "drivers"]
---

## What I Explored Today

Today I dug into Zephyr RTOS support for C++ drivers. While Zephyr's driver model is C-based (using `struct device` and `DEVICE_DEFINE` macros), the build system fully supports C++ translation units. I enabled C++ support in a Zephyr project, wrote a minimal C++ sensor driver, and wired it into the device model. The key insight: C++ classes can implement Zephyr's driver API functions, but you must handle name mangling, static constructors, and memory placement carefully.

## The Core Concept

Zephyr's driver model expects C-linkage function pointers in `struct device_driver`. C++ methods have mangled names, so you cannot directly assign a class method to a function pointer. The solution: write a C-linkage wrapper function that calls the class method through a static object. This pattern lets you use C++ features (RAII, templates, polymorphism) inside the driver while exposing a C-compatible interface to the kernel.

Why bother? C++ drivers give you:
- **RAII for hardware resources** — GPIO pins, SPI buses, and IRQs are acquired in constructors and released in destructors.
- **Template-driven peripheral access** — A single `SPIDriver<SPI_Type>` class works for multiple SPI instances.
- **Type-safe configuration** — `enum class` states and `std::optional` for error handling, no more magic numbers.

Zephyr's C++ support is opt-in. You must set `CONFIG_CPP=y` and `CONFIG_CPP_EXCEPTIONS=y` (if needed) in your project configuration. The build system then compiles `.cpp` files with the C++ compiler and links them with the Zephyr kernel.

## Key Commands / Configuration / Code

### Step 1: Enable C++ in `prj.conf`
```kconfig
# Enable C++ support
CONFIG_CPP=y
# Enable C++ exceptions (optional, adds ~12KB flash)
CONFIG_CPP_EXCEPTIONS=y
# Enable RTTI (optional, adds ~8KB flash)
CONFIG_CPP_RTTI=y
# Ensure newlib is used for C++ standard library
CONFIG_NEWLIB_LIBC=y
```

### Step 2: Minimal C++ Sensor Driver

**File: `drivers/sensor/my_sensor.cpp`**
```cpp
#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/sensor.h>
#include <zephyr/logging/log.h>
LOG_MODULE_REGISTER(my_sensor, CONFIG_SENSOR_LOG_LEVEL);

// C++ driver class with RAII
class MySensor {
public:
    MySensor(const struct device *dev) : dev_(dev) {
        // Constructor: configure GPIO, SPI, etc.
        // Called once during system initialization
        LOG_INF("MySensor constructor on %s", dev->name);
    }

    ~MySensor() {
        // Destructor: release hardware (rarely called in embedded)
    }

    int sample_fetch() {
        // Read sensor register via SPI/I2C
        // Return 0 on success, negative errno on failure
        return 0;
    }

    int get_value(struct sensor_value *val) {
        val->val1 = 42;  // Example: temperature in millidegrees
        val->val2 = 0;
        return 0;
    }

private:
    const struct device *dev_;
};

// Static instance — must be placed in kernel RAM, not .bss
static MySensor *sensor_instance;

// C-linkage wrapper functions for Zephyr driver API
extern "C" {

static int my_sensor_sample_fetch(const struct device *dev,
                                  enum sensor_channel chan) {
    ARG_UNUSED(chan);
    return sensor_instance->sample_fetch();
}

static int my_sensor_channel_get(const struct device *dev,
                                 enum sensor_channel chan,
                                 struct sensor_value *val) {
    ARG_UNUSED(chan);
    return sensor_instance->get_value(val);
}

static int my_sensor_init(const struct device *dev) {
    // Construct the C++ object — placement new in kernel memory
    sensor_instance = new (dev->data) MySensor(dev);
    return 0;
}

} // extern "C"

// Zephyr device driver API struct
static const struct sensor_driver_api my_sensor_api = {
    .sample_fetch = my_sensor_sample_fetch,
    .channel_get = my_sensor_channel_get,
};

// Device instantiation macro
#define MY_SENSOR_INIT(n)                                                  \
    static struct my_sensor_data {                                         \
        /* Placeholder for C++ object storage */                           \
        uint8_t buffer[sizeof(MySensor)];                                  \
    } my_sensor_data_##n;                                                  \
    DEVICE_DEFINE(my_sensor_##n, "MY_SENSOR" #n,                           \
                  my_sensor_init, NULL,                                    \
                  &my_sensor_data_##n, NULL,                               \
                  POST_KERNEL, CONFIG_SENSOR_INIT_PRIORITY,                \
                  &my_sensor_api)

// Instantiate for device tree node (e.g., my_sensor0)
MY_SENSOR_INIT(0);
```

### Step 3: Build and Verify
```bash
# Configure project with C++ support
west build -b nucleo_f767zi -t menuconfig
# Ensure CONFIG_CPP=y is set, then build
west build -b nucleo_f767zi
# Check that C++ symbols appear
arm-zephyr-eabi-nm build/zephyr/zephyr.elf | grep MySensor
```

## Common Pitfalls & Gotchas

1. **Static constructors in wrong memory region**  
   Zephyr's linker script places `.init_array` (static constructors) in RAM, but the kernel may not call them before `main()`. Always use placement new inside the driver init function, not global constructors. Otherwise your C++ object may be constructed twice or not at all.

2. **Exception handling blows up flash**  
   `CONFIG_CPP_EXCEPTIONS=y` pulls in unwind tables and exception personality routines. On a Cortex-M4 with 512KB flash, this can add 20-40KB. For most embedded drivers, avoid exceptions entirely — use `std::expected` or return error codes.

3. **Virtual functions and vtable placement**  
   If your driver class has virtual functions, the vtable is placed in `.rodata` by default. Ensure your linker script doesn't discard it. Add `KEEP(*(.rodata.*))` to your custom linker sections if you see "undefined reference to vtable" errors.

4. **C++ standard library dependencies**  
   Functions like `std::vector` or `std::string` pull in heap allocation. Zephyr's default heap is small (8KB). Either avoid dynamic allocation in drivers or increase `CONFIG_HEAP_MEM_POOL_SIZE`.

## Try It Yourself

1. **Enable C++ on an existing Zephyr project**  
   Take your current sensor application, add `CONFIG_CPP=y` to `prj.conf`, rename one driver file from `.c` to `.cpp`, and fix any C++ compilation errors (e.g., implicit casts, missing function prototypes).

2. **Write a C++ wrapper for a GPIO output**  
   Create a `GpioOutput` class that takes a `struct gpio_dt_spec` in its constructor, configures the pin as output, and provides a `toggle()` method. Use it in a C++ application file to blink an LED.

3. **Measure flash impact of C++ features**  
   Build three versions of the same project: (a) no C++, (b) C++ with exceptions, (c) C++ without exceptions. Compare the `.text` section size using `arm-zephyr-eabi-size`. Document the overhead.

## Next Up

Tomorrow: **MISRA C++ 2023: Key Rules & Enforcement with clang-tidy** — we'll walk through the most impactful MISRA C++ rules for embedded systems and configure clang-tidy to enforce them in a Zephyr project.
