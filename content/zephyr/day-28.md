---
title: "Day 28: Custom Board Support: DTS & Kconfig"
date: 2026-07-10
tags: ["til", "zephyr", "bsp", "board"]
---

## What I Explored Today

Today I dove into the process of creating a custom board support package (BSP) for Zephyr RTOS. This means writing the Devicetree Source (DTS) files and Kconfig fragments that tell Zephyr what hardware exists on my board and how to configure the build system. I built a minimal BSP for a hypothetical board based on the STM32F411CE — a common Cortex-M4 MCU — and got it to compile a simple blinky application. The goal was to understand the anatomy of a board directory and how Zephyr discovers and uses these files.

## The Core Concept

Zephyr’s build system uses two complementary mechanisms to describe hardware: **Devicetree** (DTS) for hardware topology and **Kconfig** for software configuration. The DTS files define what peripherals exist (e.g., UART, GPIO, SPI), their memory-mapped addresses, interrupt lines, and pinmux settings. Kconfig, on the other hand, controls which drivers and features get compiled into the kernel. The board directory (`boards/<arch>/<board_name>/`) is the glue that ties these together.

Why not just use a single configuration file? Separation of concerns. DTS is hardware-centric and often provided by silicon vendors; Kconfig is software-centric and allows you to enable/disable features without touching hardware descriptions. Zephyr’s build system merges both at compile time, generating a final `zephyr.dts` and `autoconf.h` that the driver code uses.

## Key Commands / Configuration / Code

Let’s walk through creating a board named `myboard_stm32f411`. I’ll assume you have a Zephyr workspace set up.

### 1. Board directory structure

```
boards/arm/myboard_stm32f411/
├── Kconfig.board
├── Kconfig.defconfig
├── board.cmake
├── myboard_stm32f411.dts
├── myboard_stm32f411_defconfig
└── doc/
    └── img/
```

### 2. Devicetree source (`myboard_stm32f411.dts`)

This is the core hardware description. I include the SoC’s DTSI and define board-level nodes.

```dts
/dts-v1/;
#include <st/f4/stm32f411.dtsi>
#include <st/f4/stm32f411xe.dtsi>
#include "myboard_stm32f411-pinctrl.dtsi"

/ {
	model = "MyBoard STM32F411";
	compatible = "mycompany,myboard-stm32f411";

	chosen {
		zephyr,console = &usart2;
		zephyr,shell-uart = &usart2;
		zephyr,sram = &sram0;
		zephyr,flash = &flash0;
	};

	leds {
		compatible = "gpio-leds";
		led0: led_0 {
			gpios = <&gpioc 13 GPIO_ACTIVE_LOW>;
			label = "User LED";
		};
	};

	/* Enable internal oscillator */
	clocks {
		clk_hse: clk-hse {
			compatible = "st,stm32-hse";
			clock-frequency = <8000000>;
			status = "okay";
		};
	};
};

&usart2 {
	pinctrl-0 = <&usart2_tx_pa2 &usart2_rx_pa3>;
	pinctrl-names = "default";
	current-speed = <115200>;
	status = "okay";
};
```

Notice the `pinctrl` include — that’s a separate file defining pinmux nodes. For brevity, I’ll show a snippet:

```dts
/* myboard_stm32f411-pinctrl.dtsi */
#include <dt-bindings/pinctrl/stm32-pinctrl.h>

&pinctrl {
	usart2_tx_pa2: usart2_tx_pa2 {
		pinmux = <STM32_PINMUX('A', 2, AF7)>;
	};
	usart2_rx_pa3: usart2_rx_pa3 {
		pinmux = <STM32_PINMUX('A', 3, AF7)>;
	};
};
```

### 3. Kconfig files

**Kconfig.board** — declares the board symbol:

```kconfig
config BOARD_MYBOARD_STM32F411
	bool "MyBoard STM32F411"
	depends on SOC_STM32F411XE
```

**Kconfig.defconfig** — default settings for this board:

```kconfig
if BOARD_MYBOARD_STM32F411

config BOARD
	default "myboard_stm32f411"

config UART_CONSOLE
	default y

config SERIAL
	default y

endif # BOARD_MYBOARD_STM32F411
```

**myboard_stm32f411_defconfig** — minimal defconfig for a blinky build:

```kconfig
CONFIG_BOARD_MYBOARD_STM32F411=y
CONFIG_GPIO=y
CONFIG_SERIAL=y
CONFIG_UART_CONSOLE=y
CONFIG_PRINTK=y
```

### 4. Build and test

```bash
# Set up environment
source zephyr-env.sh

# Build blinky for our board
west build -b myboard_stm32f411 zephyr/samples/basic/blinky

# Flash (assuming openocd support)
west flash
```

If you get a “board not found” error, verify your board directory is under `boards/arm/` and the name matches exactly.

## Common Pitfalls & Gotchas

1. **Missing pinctrl nodes cause silent boot hangs.** If your UART or SPI doesn’t have a `pinctrl-0` property with a valid pinmux, the driver will probe but never actually work. Always double-check the pinmux macros — they’re SoC-specific. Use `STM32_PINMUX(port, pin, alternate_function)` for STM32.

2. **Kconfig dependencies are not automatically resolved.** If you enable `CONFIG_SERIAL` but forget `CONFIG_UART_CONSOLE`, the console won’t appear. Worse, if your DTS enables a peripheral but the corresponding Kconfig symbol isn’t set, the driver won’t be compiled. Always run `west build -t menuconfig` to verify your settings.

3. **Board name collisions.** Zephyr’s board detection uses the `-b` flag, which matches against the directory name. If you name your board `stm32f411`, it will conflict with the official ST boards. Prefix with your company/vendor name (e.g., `myboard_stm32f411`).

## Try It Yourself

1. **Create a minimal board directory** for a different MCU (e.g., nRF52840). Use the official nRF52840 DK DTS as a reference. Start with just UART and GPIO, then build the `hello_world` sample.

2. **Add a custom LED node** to your DTS and write a simple application that toggles it using `gpio_pin_configure()` and `gpio_pin_set()`. Verify the pinmux matches your hardware.

3. **Debug a broken UART.** Intentionally remove the `pinctrl-0` property from your DTS, build, and flash. Observe that the board boots but no console output appears. Then fix it by adding the correct pinctrl node.

## Next Up

Tomorrow, we’ll take this board support to the next level: **Writing a Custom Zephyr Driver**. We’ll implement a simple sensor driver that uses the devicetree and Kconfig infrastructure we just built, complete with API registration and power management hooks.
