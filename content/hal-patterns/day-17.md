---
title: "Day 17: Board Support Packages: Structuring Board-Specific Code"
date: 2026-07-17
tags: ["til", "hal-patterns", "bsp"]
---

## What I Explored Today

Today I dug into Board Support Packages (BSPs) — the layer that sits between the HAL and the actual hardware on a specific PCB. While the HAL abstracts the MCU peripherals generically, the BSP owns everything that makes *your board* unique: pin mappings, external device addresses, oscillator frequencies, and power sequencing. I refactored a messy `main.c` that had GPIO numbers and I2C addresses scattered everywhere into a proper BSP structure, and the result is a codebase where porting to a hardware revision means editing one header file instead of chasing constants through 20 source files.

## The Core Concept

A BSP is not a driver. A driver knows *how* to talk to a peripheral (e.g., "write this register sequence to initialize the SPI bus"). A BSP knows *what* to talk to and *where it is* on this particular board (e.g., "the temperature sensor is at I2C address 0x48 on bus I2C2, using SCL on PB10 and SDA on PB11").

The key insight: **board-specific knowledge should never leak into the HAL or application layers.** If you change a resistor divider on an ADC input channel, you should only touch the BSP. If you swap the MCU package but keep the same peripherals, you change the HAL — not the BSP. This separation is what makes firmware portable across hardware revisions and even across MCU families.

A well-structured BSP provides:
- Pin definitions (port, pin number, alternate function)
- External device addresses and bus assignments
- Board-level initialization sequences (clock tree, power rails, reset lines)
- Board-specific constants (reference voltages, calibration values)

## Key Commands / Configuration / Code

Here's the BSP structure I settled on after today's refactor:

```
board/
├── bsp.h                  # Master include — every file includes this
├── bsp_pins.h             # Pin mappings only
├── bsp_devices.h          # External device addresses & bus assignments
├── bsp_init.c             # Board-level initialization
└── bsp_init.h
```

**bsp_pins.h** — one source of truth for every pin:

```c
// bsp_pins.h — all pin assignments in one place
#ifndef BSP_PINS_H
#define BSP_PINS_H

#include "hal_gpio.h"  // HAL GPIO types

// LED on PA5 — active high
#define BSP_LED_PORT    GPIOA
#define BSP_LED_PIN     5
#define BSP_LED_ON()    hal_gpio_write(BSP_LED_PORT, BSP_LED_PIN, 1)
#define BSP_LED_OFF()   hal_gpio_write(BSP_LED_PORT, BSP_LED_PIN, 0)

// UART1 on PA9 (TX) / PA10 (RX)
#define BSP_UART_TX_PORT    GPIOA
#define BSP_UART_TX_PIN     9
#define BSP_UART_TX_AF      7       // Alternate function for USART1
#define BSP_UART_RX_PORT    GPIOA
#define BSP_UART_RX_PIN     10
#define BSP_UART_RX_AF      7

// I2C1 for on-board sensor bus — PB6 (SCL) / PB7 (SDA)
#define BSP_SENSOR_I2C      I2C1
#define BSP_SENSOR_SCL_PORT GPIOB
#define BSP_SENSOR_SCL_PIN  6
#define BSP_SENSOR_SDA_PORT GPIOB
#define BSP_SENSOR_SDA_PIN  7

#endif
```

**bsp_devices.h** — external component locations:

```c
// bsp_devices.h — addresses and bus ownership
#ifndef BSP_DEVICES_H
#define BSP_DEVICES_H

#include "hal_i2c.h"

// Temperature sensor (TMP117) on sensor I2C bus
#define BSP_TEMP_SENSOR_ADDR    0x48
#define BSP_TEMP_SENSOR_BUS     BSP_SENSOR_I2C

// EEPROM (24LC256) on same bus, different address
#define BSP_EEPROM_ADDR         0x50
#define BSP_EEPROM_BUS          BSP_SENSOR_I2C

// External ADC (ADS1115) on dedicated I2C2 bus
#define BSP_EXT_ADC_ADDR        0x4A
#define BSP_EXT_ADC_BUS         I2C2

#endif
```

**bsp_init.c** — board-level initialization that the HAL doesn't know about:

```c
// bsp_init.c — board-specific power-up sequence
#include "bsp.h"
#include "hal_gpio.h"
#include "hal_rcc.h"   // Reset and clock control

void bsp_init(void) {
    // 1. Set system clock to 168 MHz (board-specific crystal + PLL config)
    hal_rcc_configure_hse(8000000);          // 8 MHz external crystal
    hal_rcc_configure_pll(HSE, 168000000);   // PLL to 168 MHz
    hal_rcc_sysclk_select(PLL);

    // 2. Enable GPIO clocks for all used ports
    hal_rcc_gpio_enable(GPIOA);
    hal_rcc_gpio_enable(GPIOB);

    // 3. Configure LED pin as push-pull output
    hal_gpio_set_mode(BSP_LED_PORT, BSP_LED_PIN, GPIO_MODE_OUTPUT_PP);
    hal_gpio_set_speed(BSP_LED_PORT, BSP_LED_PIN, GPIO_SPEED_LOW);

    // 4. Configure UART pins with alternate function
    hal_gpio_set_mode(BSP_UART_TX_PORT, BSP_UART_TX_PIN, GPIO_MODE_AF_PP);
    hal_gpio_set_af(BSP_UART_TX_PORT, BSP_UART_TX_PIN, BSP_UART_TX_AF);
    hal_gpio_set_mode(BSP_UART_RX_PORT, BSP_UART_RX_PIN, GPIO_MODE_AF_IN);
    hal_gpio_set_af(BSP_UART_RX_PORT, BSP_UART_RX_PIN, BSP_UART_RX_AF);

    // 5. Power up external sensor (board-specific GPIO controls sensor VCC)
    hal_gpio_set_mode(GPIOC, 0, GPIO_MODE_OUTPUT_PP);
    hal_gpio_write(GPIOC, 0, 1);   // Enable sensor power
    hal_delay_ms(10);               // Wait for power rail to stabilize

    // 6. Initialize I2C bus for sensors
    hal_i2c_init(BSP_SENSOR_I2C, 100000);  // 100 kHz standard mode
}
```

The application code then never references raw GPIO ports or I2C addresses:

```c
// application.c — clean, BSP-aware code
#include "bsp.h"
#include "tmp117.h"   // sensor driver

void read_temperature(void) {
    float temp_c;
    // No GPIOs, no addresses — just BSP constants
    tmp117_read(BSP_TEMP_SENSOR_BUS, BSP_TEMP_SENSOR_ADDR, &temp_c);
    if (temp_c > 85.0f) {
        BSP_LED_ON();
    }
}
```

## Common Pitfalls & Gotchas

**1. Mixing BSP and HAL responsibilities.** I've seen BSPs that try to initialize the SPI peripheral itself, including clock divider calculations. That's the HAL's job. The BSP should only say "SPI1 at 1 MHz, CS on PA4" — not configure the SPI registers directly. Keep the BSP declarative, not procedural.

**2. Hardcoding magic numbers in application code.** If you write `I2C1` or `0x48` directly in a sensor read function, you've created a hidden dependency. When the next board revision moves the sensor to I2C2 at address 0x49, you'll be hunting through every `.c` file. Always use BSP macros, even if they seem like "obvious" constants.

**3. Forgetting that BSPs must be board-revision aware.** A good BSP uses conditional compilation for hardware variants:
```c
#if defined(REV_B)
    #define BSP_TEMP_SENSOR_ADDR    0x49
#else
    #define BSP_TEMP_SENSOR_ADDR    0x48
#endif
```
Without this, you'll end up with separate BSP directories for each revision, duplicating 90% of the code.

## Try It Yourself

1. **Audit your current project.** Find every raw GPIO number, peripheral base address, or I2C address that appears in application code. Move them all into a single `bsp_pins.h` and `bsp_devices.h`. Verify the application compiles with zero changes to peripheral addresses.

2. **Create a board revision macro.** Add `#if defined(REV_A)` / `#elif defined(REV_B)` blocks to your BSP for at least one pin or address that differs between revisions. Build both configurations from the same source tree.

3. **Write a BSP validation test.** Create a `bsp_selftest()` function that toggles every output pin, reads back every input, and probes each I2C address for an ACK. Call it once at startup during development — it catches wiring errors in seconds.

## Next Up

Tomorrow: **Peripheral Drivers as Reusable Components: Versioning & APIs** — how to design driver interfaces that survive MCU migrations, why semantic versioning matters for firmware libraries, and the one header trick that prevents API breakage across projects.
