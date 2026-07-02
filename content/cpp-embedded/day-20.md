---
title: "Day 20: Full Review & Project: C++ HAL for a Sensor Driver"
date: 2026-07-02
tags: ["til", "cpp-embedded", "review", "project", "hal"]
---

## What I Explored Today

Today we tie together everything from the past 19 days into a single, cohesive project: a C++ Hardware Abstraction Layer (HAL) for a real-world sensor driver. We'll build a driver for the BME280 environmental sensor (temperature, humidity, pressure) that runs on a Cortex-M4 MCU. This isn't a toy example — it uses `constexpr` for calibration constants, `std::span` for register access, `std::expected` for error handling, and a polymorphic I2C abstraction. The goal is to demonstrate how modern C++ can produce a driver that is type-safe, testable, and zero-overhead compared to C, while being far more maintainable.

## The Core Concept

A HAL is the boundary between hardware-specific code and application logic. In embedded systems, the HAL must be:
- **Zero-cost**: No virtual dispatch or dynamic allocation in the hot path
- **Portable**: Swap the I2C backend (hardware vs. mock) without changing sensor logic
- **Error-propagating**: Hardware can fail; the type system should enforce handling

The key insight: we separate *interface* from *implementation* using templates and concepts, not virtual functions. This gives compile-time polymorphism — the compiler sees the exact call chain and inlines everything. The sensor driver never knows whether it's talking to real hardware or a test mock.

## Key Commands / Configuration / Code

### 1. The I2C Abstraction (Concept-based)

```cpp
#include <concepts>
#include <cstdint>
#include <span>

// Concept for any I2C bus implementation
template<typename T>
concept I2CBus = requires(T& bus, uint8_t addr, std::span<const uint8_t> tx, std::span<uint8_t> rx) {
    { bus.write(addr, tx) } -> std::same_as<bool>;
    { bus.read(addr, rx) } -> std::same_as<bool>;
    { bus.write_read(addr, tx, rx) } -> std::same_as<bool>;
};
```

### 2. BME280 Driver (Template-based, no virtual)

```cpp
#include <expected>
#include <array>
#include <algorithm>

enum class BmeError { 
    CommunicationFailed, 
    InvalidChipId, 
    CalibrationCorrupt 
};

template<I2CBus Bus>
class Bme280 {
public:
    static constexpr uint8_t ADDR = 0x76;  // Default I2C address
    static constexpr uint8_t CHIP_ID_REG = 0xD0;
    static constexpr uint8_t CHIP_ID_EXPECTED = 0x60;

    struct CalibrationData {
        uint16_t dig_T1;
        int16_t dig_T2, dig_T3;
        // ... (pressure/humidity coefficients omitted for brevity)
    };

    // Constructor takes bus reference, not ownership
    explicit Bme280(Bus& bus) : bus_(bus) {}

    std::expected<CalibrationData, BmeError> init() {
        // Read chip ID to verify connection
        uint8_t chip_id;
        if (!read_reg(CHIP_ID_REG, chip_id)) {
            return std::unexpected(BmeError::CommunicationFailed);
        }
        if (chip_id != CHIP_ID_EXPECTED) {
            return std::unexpected(BmeError::InvalidChipId);
        }

        // Read calibration data (stored at fixed registers 0x88-0xA1)
        std::array<uint8_t, 24> cal_raw;
        if (!read_regs(0x88, cal_raw)) {
            return std::unexpected(BmeError::CommunicationFailed);
        }

        CalibrationData cal;
        cal.dig_T1 = static_cast<uint16_t>(cal_raw[0]) | 
                     (static_cast<uint16_t>(cal_raw[1]) << 8);
        cal.dig_T2 = static_cast<int16_t>(cal_raw[2]) | 
                     (static_cast<int16_t>(cal_raw[3]) << 8);
        cal.dig_T3 = static_cast<int16_t>(cal_raw[4]) | 
                     (static_cast<int16_t>(cal_raw[5]) << 8);

        // Validate calibration (T1 must not be zero)
        if (cal.dig_T1 == 0) {
            return std::unexpected(BmeError::CalibrationCorrupt);
        }

        return cal;
    }

    std::expected<int32_t, BmeError> read_temperature_raw() {
        std::array<uint8_t, 3> raw;
        if (!read_regs(0xFA, raw)) {
            return std::unexpected(BmeError::CommunicationFailed);
        }
        return static_cast<int32_t>(raw[0]) << 12 | 
               static_cast<int32_t>(raw[1]) << 4 | 
               static_cast<int32_t>(raw[2]) >> 4;
    }

private:
    Bus& bus_;

    bool read_reg(uint8_t reg, uint8_t& value) {
        std::array<uint8_t, 1> tx = {reg};
        std::array<uint8_t, 1> rx = {};
        if (!bus_.write_read(ADDR, tx, rx)) return false;
        value = rx[0];
        return true;
    }

    bool read_regs(uint8_t start_reg, std::span<uint8_t> buffer) {
        std::array<uint8_t, 1> tx = {start_reg};
        return bus_.write_read(ADDR, tx, buffer);
    }
};
```

### 3. Concrete I2C Implementation (STM32 HAL)

```cpp
#include "stm32g4xx_hal.h"

class Stm32I2c {
public:
    explicit Stm32I2c(I2C_HandleTypeDef& hi2c) : hi2c_(hi2c) {}

    bool write(uint8_t addr, std::span<const uint8_t> data) {
        return HAL_I2C_Master_Transmit(&hi2c_, addr << 1, 
               const_cast<uint8_t*>(data.data()), data.size(), 100) == HAL_OK;
    }

    bool read(uint8_t addr, std::span<uint8_t> data) {
        return HAL_I2C_Master_Receive(&hi2c_, addr << 1, 
               data.data(), data.size(), 100) == HAL_OK;
    }

    bool write_read(uint8_t addr, std::span<const uint8_t> tx, 
                    std::span<uint8_t> rx) {
        return write(addr, tx) && read(addr, rx);
    }

private:
    I2C_HandleTypeDef& hi2c_;
};
```

### 4. Usage in Application

```cpp
// main.cpp
I2C_HandleTypeDef hi2c1;  // Initialized by HAL_Init()
Stm32I2c i2c_bus(hi2c1);
Bme280<Stm32I2c> sensor(i2c_bus);

auto cal = sensor.init();
if (!cal) {
    // Handle error: cal.error() returns BmeError enum
    ErrorHandler(static_cast<int>(cal.error()));
}

auto temp_raw = sensor.read_temperature_raw();
if (temp_raw) {
    // Compensate using calibration data
    float temp = compensate_temperature(*temp_raw, *cal);
}
```

## Common Pitfalls & Gotchas

1. **I2C Address Shift**: STM32 HAL expects 7-bit addresses shifted left by 1 (8-bit format). The BME280's 0x76 becomes 0xEC for HAL. Always check your MCU's I2C driver documentation — this mismatch causes silent failures.

2. **Calibration Data Endianness**: The BME280 stores multi-byte values in little-endian order. On a Cortex-M4 (also little-endian), a naive `memcpy` works, but if you ever port to a big-endian target (rare, but possible), you'll get garbage. Always explicitly assemble bytes as shown above.

3. **Template Bloat**: Each instantiation of `Bme280<Bus>` creates separate code. If you have multiple BME280s on different I2C buses, consider if you need separate types or if a single type with a bus reference suffices. The latter is usually better for code size.

## Try It Yourself

1. **Add a mock I2C bus** that returns predefined data. Write a unit test that verifies `init()` returns `InvalidChipId` when the mock returns 0xFF for the chip ID register.

2. **Extend the driver** to read humidity. The humidity registers are at 0xFD (2 bytes). Add a `read_humidity_raw()` method that returns `std::expected<uint16_t, BmeError>`.

3. **Measure code size**: Compile the driver with `-Os` for your target MCU. Compare the `.text` section size against an equivalent C implementation using function pointers. Note the difference (should be zero or negative — templates inline better).

## Next Up

Day 21: Full Review — We'll step back and map the entire C++ for Embedded journey: from `constexpr` and templates to RAII and concepts. We'll identify the top 5 patterns that gave the biggest reliability and performance wins, and where C++ still falls short for embedded. Bring your toughest questions.
