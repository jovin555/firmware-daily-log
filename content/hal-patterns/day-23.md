---
title: "Day 23: Anti-Patterns: God Objects, Leaky Abstractions & Over-Engineering"
date: 2026-07-23
tags: ["til", "hal-patterns", "anti-patterns"]
---

## What I Explored Today

After 22 days of building clean HAL abstractions, I spent today studying the wreckage. Not literally—but I audited three production firmware projects that had been "improved" over several years. Each one exhibited classic anti-patterns: a single struct that knew everything (God Object), a SPI abstraction that silently fell back to bit-banging (Leaky Abstraction), and a GPIO driver with virtual inheritance for "future-proofing" that never shipped (Over-Engineering). Today’s log catalogs these three traps, why they happen, and how to spot them before they metastasize.

## The Core Concept

Anti-patterns are not just bad code—they are *deceptively attractive* solutions that solve an immediate problem while creating long-term debt. In embedded systems, where memory is constrained and timing is critical, these patterns are especially dangerous.

**God Objects** emerge when you centralize state for convenience. A single `SystemContext` struct that holds the ADC handle, the timer callback pointer, the UART buffer, and the LED blink counter feels efficient. But it creates a coupling nightmare: every module now depends on this monolithic struct, and changing one field risks breaking unrelated features. The real cost is in testing—you can’t unit-test a sensor driver without instantiating the entire system.

**Leaky Abstractions** happen when a wrapper promises platform independence but exposes platform-specific behavior. The classic example: a `spi_transfer()` function that works on STM32 but silently uses a different clock polarity on NXP because the HAL’s `SPI_InitStruct` default differs. The abstraction *leaks* because it didn’t fully capture the contract. Engineers then add conditional `#ifdef` blocks, and the abstraction becomes a tangled mess of platform hacks.

**Over-Engineering** is the seductive trap of solving problems you don’t yet have. A GPIO driver with a polymorphic interface, a factory pattern for timers, and a state machine for pin configuration—all for a product that only needs to toggle an LED. The cost is compile-time bloat, runtime overhead, and cognitive load for the next engineer who just wants to blink a pin.

The common thread: each anti-pattern trades *short-term convenience* for *long-term fragility*. The fix is discipline: keep objects focused, document abstraction contracts explicitly, and resist adding features until the requirement is concrete.

## Key Commands / Configuration / Code

### God Object Example (Avoid This)

```c
// god_object.h — BAD: monolithic struct
typedef struct {
    SPI_HandleTypeDef hspi1;
    UART_HandleTypeDef huart2;
    ADC_HandleTypeDef hadc1;
    TIM_HandleTypeDef htim3;
    uint8_t sensor_buffer[256];
    uint32_t system_ticks;
    void (*error_callback)(uint32_t error_code);
} SystemContext;

SystemContext ctx; // Every module accesses this
```

**Better approach:** Decompose into focused driver instances.

```c
// sensor_driver.h — GOOD: focused abstraction
typedef struct {
    SPI_HandleTypeDef *hspi;  // Only what sensor needs
    uint32_t cs_pin;
    GPIO_TypeDef *cs_port;
    uint32_t timeout_ms;
} Sensor_Config;

Sensor_Handle Sensor_Init(Sensor_Config *cfg);
int32_t Sensor_ReadData(Sensor_Handle *handle, uint8_t *buf, uint16_t len);
```

### Leaky Abstraction Example

```c
// leaky_spi.h — BAD: no contract enforcement
int32_t SPI_Transfer(uint8_t *tx, uint8_t *rx, uint16_t len);
// On STM32: CPOL=0, CPHA=0 (mode 0)
// On NXP: CPOL=1, CPHA=1 (mode 3) — SILENTLY DIFFERENT
```

**Better approach:** Explicit contract in the API.

```c
// spi_contract.h — GOOD: documented and enforced
typedef enum {
    SPI_MODE_0 = 0,  // CPOL=0, CPHA=0
    SPI_MODE_1 = 1,  // CPOL=0, CPHA=1
    SPI_MODE_2 = 2,  // CPOL=1, CPHA=0
    SPI_MODE_3 = 3   // CPOL=1, CPHA=1
} SPI_Mode;

typedef struct {
    uint32_t clock_hz;
    SPI_Mode mode;
    bool msb_first;
    uint32_t cs_to_clock_delay_us;
} SPI_Config;

int32_t SPI_Init(SPI_Config *cfg);  // Must match exactly
int32_t SPI_Transfer(uint8_t *tx, uint8_t *rx, uint16_t len);
```

### Over-Engineering Example

```c
// over_engineered_gpio.h — BAD: virtual inheritance for a pin toggle
typedef struct GPIO_Interface {
    void (*set)(void *self, bool state);
    void (*toggle)(void *self);
    bool (*read)(void *self);
} GPIO_Interface;

typedef struct {
    GPIO_Interface vtable;
    GPIO_TypeDef *port;
    uint16_t pin;
} VirtualGPIO;

// 50 lines of boilerplate to call: HAL_GPIO_TogglePin(LED_PORT, LED_PIN);
```

**Better approach:** Simple, direct, testable.

```c
// gpio_driver.h — GOOD: straightforward
typedef struct {
    GPIO_TypeDef *port;
    uint16_t pin;
} GPIO_Pin;

static inline void GPIO_Set(GPIO_Pin *p, bool state) {
    HAL_GPIO_WritePin(p->port, p->pin, state ? GPIO_PIN_SET : GPIO_PIN_RESET);
}

static inline void GPIO_Toggle(GPIO_Pin *p) {
    HAL_GPIO_TogglePin(p->port, p->pin);
}
```

## Common Pitfalls & Gotchas

1. **The "One More Field" Trap with God Objects**  
   It starts innocently: "I'll just add one more pointer to the system struct." After six months, the struct is 2KB, and every file includes it. When you need to change the timer callback signature, you recompile the entire project. **Mitigation:** Enforce a rule—each struct must serve exactly one driver or module. If it has more than 5 fields that aren't configuration, refactor.

2. **Silent Fallback in Leaky Abstractions**  
   I’ve seen an I2C abstraction that, when the hardware peripheral was busy, silently switched to bit-banging on the same pins. The timing changed, and a sensor started returning garbage. No error was raised. **Mitigation:** Every abstraction must document its failure modes. If a fallback exists, it must be explicit (e.g., return `-EBUSY` and let the caller decide).

3. **The "We Might Need It" Premature Abstraction**  
   Over-engineering often hides behind "extensibility." A junior engineer adds a polymorphic timer interface because "we might support FreeRTOS later." Two years later, the project still uses bare metal, and the vtable overhead costs 12 bytes per timer instance. **Mitigation:** Only abstract when you have *two concrete implementations* in hand. YAGNI (You Ain’t Gonna Need It) is a law, not a suggestion.

## Try It Yourself

1. **Audit a God Object**  
   Find the largest struct in your current firmware project. List every module that accesses it. For each field, ask: "Does this field belong to this struct, or should it be in a dedicated driver struct?" Refactor one field into its own focused struct.

2. **Test Your SPI Abstraction**  
   Write a test that calls `SPI_Transfer()` with a known pattern on two different MCU families (e.g., STM32 and NXP). Verify the clock polarity, phase, and data order match exactly. If they don’t, update your config struct to enforce the contract.

3. **Remove an Unused Abstraction**  
   Find one piece of code that uses virtual functions, function pointers, or inheritance for a feature that has only one implementation. Replace it with a direct call. Measure the code size savings (use `size` or map file analysis).

## Next Up

Tomorrow is Day 24: **Full Review & Project: Vendor-Agnostic SPI Sensor Driver**. We’ll take everything from the past 23 days and build a complete, production-ready SPI sensor driver that works on STM32, NXP, and Microchip—without a single `#ifdef`. Bring your datasheets and a willingness to refactor.
