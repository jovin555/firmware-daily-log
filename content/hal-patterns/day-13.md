---
title: "Day 13: Factory Pattern for Peripheral Driver Instantiation"
date: 2026-07-13
tags: ["til", "hal-patterns", "factory-pattern"]
---

## What I Explored Today

Today I tackled a recurring pain point in embedded C++: how to instantiate the correct peripheral driver when the hardware variant isn't known until runtime. Whether it's selecting between an internal ADC and an external I2C ADC, or choosing a UART driver for a chip that has multiple silicon revisions, the factory pattern provides a clean, testable solution. I implemented a peripheral driver factory that decouples driver selection from driver usage, and I'm sharing the concrete approach I used on an STM32L4 target.

## The Core Concept

The factory pattern solves a specific problem: you have a family of related driver classes (all implementing the same interface), and you need to create one of them based on runtime conditions. In embedded systems, those conditions might be:

- Board revision detected from a GPIO strapping pin
- Chip variant read from a device ID register
- External hardware detected via a probe sequence
- Configuration loaded from EEPROM or flash

Without a factory, you end up with `#ifdef` chains or switch statements scattered across your application code. The factory centralizes this decision logic into one place. The key insight is that the caller doesn't need to know *which* concrete driver it's using — it only needs the interface. This enables unit testing with mock drivers, runtime reconfiguration, and clean separation of hardware abstraction from business logic.

The factory itself is typically a static method or a standalone function that returns a pointer (or smart pointer) to the interface. In embedded C++, I prefer returning a `std::unique_ptr` for automatic lifetime management, or a raw pointer if you're in a bare-metal environment without the STL.

## Key Commands / Configuration / Code

Here's the concrete implementation I used today. The target is an STM32L476RG, and I'm abstracting a temperature sensor driver that could be either an internal sensor or an external TMP102 over I2C.

First, the interface that all drivers must implement:

```cpp
// itemperature_sensor.h
class ITemperatureSensor {
public:
    virtual ~ITemperatureSensor() = default;
    virtual float read_celsius() = 0;
    virtual bool init() = 0;
    virtual void deinit() = 0;
};
```

Now two concrete implementations:

```cpp
// internal_temp_sensor.h
#include "itemperature_sensor.h"
#include "stm32l4xx_hal.h"

class InternalTempSensor : public ITemperatureSensor {
public:
    InternalTempSensor(ADC_HandleTypeDef* hadc) : hadc_(hadc) {}
    
    bool init() override {
        // Enable internal temperature sensor
        LL_ADC_SetCommonPathInternalCh(__LL_ADC_COMMON_INSTANCE(hadc_->Instance),
                                       LL_ADC_PATH_INTERNAL_TEMPSENSOR);
        return HAL_ADC_Init(hadc_) == HAL_OK;
    }
    
    float read_celsius() override {
        uint32_t adc_val;
        HAL_ADC_Start(hadc_);
        HAL_ADC_PollForConversion(hadc_, 100);
        adc_val = HAL_ADC_GetValue(hadc_);
        HAL_ADC_Stop(hadc_);
        // STM32L4 formula: Temp = ((TS_DATA - TS_CAL1) * (110 - 30) / (TS_CAL2 - TS_CAL1)) + 30
        return ((float)adc_val - *TS_CAL1_ADDR) * 80.0f / 
               ((float)*TS_CAL2_ADDR - *TS_CAL1_ADDR) + 30.0f;
    }
    
    void deinit() override {
        HAL_ADC_DeInit(hadc_);
    }
    
private:
    ADC_HandleTypeDef* hadc_;
};
```

```cpp
// external_temp_sensor.h
#include "itemperature_sensor.h"

class ExternalTempSensor : public ITemperatureSensor {
public:
    ExternalTempSensor(I2C_HandleTypeDef* hi2c, uint8_t addr) 
        : hi2c_(hi2c), addr_(addr << 1) {}  // 7-bit to 8-bit for HAL
    
    bool init() override {
        uint8_t config = 0x60;  // 12-bit resolution, normal mode
        return HAL_I2C_Mem_Write(hi2c_, addr_, 0x01, I2C_MEMADD_SIZE_8BIT,
                                 &config, 1, 100) == HAL_OK;
    }
    
    float read_celsius() override {
        uint8_t buf[2];
        if (HAL_I2C_Mem_Read(hi2c_, addr_, 0x00, I2C_MEMADD_SIZE_8BIT,
                             buf, 2, 100) != HAL_OK) {
            return -273.15f;  // Return absolute zero on error
        }
        int16_t raw = (buf[0] << 8) | buf[1];
        return raw * 0.0625f;  // TMP102: 1 LSB = 0.0625°C
    }
    
    void deinit() override {
        // Put sensor into shutdown mode
        uint8_t config = 0x61;
        HAL_I2C_Mem_Write(hi2c_, addr_, 0x01, I2C_MEMADD_SIZE_8BIT,
                          &config, 1, 100);
    }
    
private:
    I2C_HandleTypeDef* hi2c_;
    uint8_t addr_;
};
```

And the factory itself:

```cpp
// temp_sensor_factory.h
#include <memory>
#include "itemperature_sensor.h"

class TempSensorFactory {
public:
    enum class SensorType {
        INTERNAL,
        EXTERNAL_TMP102
    };
    
    static std::unique_ptr<ITemperatureSensor> create(
        SensorType type,
        void* hw_handle1,
        void* hw_handle2 = nullptr) {
        
        switch (type) {
            case SensorType::INTERNAL:
                return std::make_unique<InternalTempSensor>(
                    static_cast<ADC_HandleTypeDef*>(hw_handle1));
                
            case SensorType::EXTERNAL_TMP102:
                return std::make_unique<ExternalTempSensor>(
                    static_cast<I2C_HandleTypeDef*>(hw_handle1),
                    hw_handle2 ? *static_cast<uint8_t*>(hw_handle2) : 0x48);
                
            default:
                return nullptr;
        }
    }
};
```

Usage in application code:

```cpp
// main.cpp
#include "temp_sensor_factory.h"

int main() {
    HAL_Init();
    
    // Board revision detection via GPIO
    GPIO_PinState rev_pin = HAL_GPIO_ReadPin(GPIOA, GPIO_PIN_0);
    
    auto sensor = TempSensorFactory::create(
        (rev_pin == GPIO_PIN_SET) 
            ? TempSensorFactory::SensorType::INTERNAL
            : TempSensorFactory::SensorType::EXTERNAL_TMP102,
        &hadc1, 
        (void*)&tmp102_addr);
    
    if (!sensor || !sensor->init()) {
        Error_Handler();
    }
    
    float temp = sensor->read_celsius();
    // ... application logic ...
    
    sensor->deinit();
}
```

## Common Pitfalls & Gotchas

1. **Raw pointer casts are dangerous.** In the factory, I'm using `void*` and `static_cast` to pass hardware handles. This is common in embedded C++ but requires discipline. If you pass the wrong handle type (e.g., an `I2C_HandleTypeDef*` where an `ADC_HandleTypeDef*` is expected), you get undefined behavior. Consider using `std::variant` or a tagged union if your toolchain supports C++17.

2. **Factory ownership semantics.** Returning `std::unique_ptr` is clean, but many embedded projects avoid the STL due to code size or exception concerns. In that case, return a raw pointer and document that the caller owns the memory. Alternatively, use a static pool allocator with placement new to avoid heap fragmentation.

3. **Hardware initialization order.** The factory creates the driver object, but `init()` is called separately. This is intentional — it allows the caller to handle errors gracefully. However, ensure that the HAL handles passed to the factory are already initialized (e.g., `MX_ADC1_Init()` called before factory creation). I've debugged many hours of "sensor not responding" that turned out to be a clock not yet enabled.

## Try It Yourself

1. **Extend the factory** to support a third sensor type, such as an LM75 over I2C. Add the enum value, implement the class, and update the factory switch statement. Test by toggling the board revision pin.

2. **Replace `std::unique_ptr` with a static pool.** Create a fixed-size array of `InternalTempSensor` and `ExternalTempSensor` instances. Use placement new in the factory and a custom deleter. Measure the heap savings compared to dynamic allocation.

3. **Add a probe-based factory method.** Instead of taking an enum, write a `TempSensorFactory::detect_and_create()` that tries to communicate with the external sensor first. If it ACKs, return an `ExternalTempSensor`; otherwise fall back to the internal sensor. This is how many real products auto-detect hardware revisions.

## Next Up

Tomorrow I'll formalize the **Device Driver Model** — the four fundamental contracts every peripheral driver should implement: Init, Configure, Read/Write, and Deinit. We'll look at how these map to real HALs and why this contract-based approach prevents the "spaghetti initialization" that plagues so many firmware projects.
