---
title: "Day 07: Common Bindings: GPIO, I2C, SPI, UART & Regulators"
date: 2026-06-19
tags: ["til", "devicetree", "gpio", "i2c", "spi", "uart", "regulators"]
---

## What I Explored Today

Today I dug into the standard Device Tree bindings for the five most common peripheral interfaces: GPIO, I2C, SPI, UART, and voltage regulators. While each subsystem has its own quirks, they all follow a consistent pattern of `#*-cells`, `pinctrl-*`, and interrupt mapping. Understanding these bindings is essential because they appear in nearly every board DTS file, and getting them wrong means silent probe failures or unstable hardware.

## The Core Concept

The Device Tree binding for each peripheral serves as a contract between the hardware description and the kernel driver. The binding defines:

1. **How to address resources** — which pins, which bus instance, which chip select
2. **How to configure the hardware** — pin muxing, speed, polarity
3. **How to handle interrupts** — which interrupt controller, which line, edge vs. level

The `#*-cells` pattern (e.g., `#gpio-cells = <2>`) tells the DT parser how many 32-bit integers are needed to describe a single resource reference. For GPIOs, two cells typically encode the pin number and active-low flag. For interrupts, two cells encode the interrupt number and trigger type.

The `pinctrl-*` properties link the device node to the pin controller configuration. This is where most engineers get tripped up — the pin controller node defines the muxing, but the *consumer* node references it via `pinctrl-names` and `pinctrl-0`.

## Key Commands / Configuration / Code

### GPIO Binding Example (Consumer)

```dts
// GPIO controller node (inside SoC)
gpio0: gpio@ff708000 {
    compatible = "rockchip,gpio-bank";
    reg = <0x0 0xff708000 0x0 0x100>;
    interrupts = <GIC_SPI 16 IRQ_TYPE_LEVEL_HIGH>;
    clocks = <&clk_gpio0>;
    
    gpio-controller;
    #gpio-cells = <2>;  // pin number + flags
    
    interrupt-controller;
    #interrupt-cells = <2>; // interrupt number + type
};

// Consumer: an LED on GPIO0_A1 (pin 1), active high
led-heartbeat {
    compatible = "gpio-leds";
    led-0 {
        gpios = <&gpio0 RK_PA1 GPIO_ACTIVE_HIGH>;
        linux,default-trigger = "heartbeat";
    };
};
```

### I2C Binding Example

```dts
// I2C controller
i2c1: i2c@ff160000 {
    compatible = "rockchip,rk3399-i2c";
    reg = <0x0 0xff160000 0x0 0x1000>;
    interrupts = <GIC_SPI 33 IRQ_TYPE_LEVEL_HIGH>;
    clocks = <&clk_i2c1>, <&clk_i2c1>;
    clock-names = "i2c", "pclk";
    
    pinctrl-names = "default";
    pinctrl-0 = <&i2c1_xfer>;  // pin muxing from pinctrl node
    
    #address-cells = <1>;
    #size-cells = <0>;
    
    // Child device: temperature sensor at address 0x48
    temp_sensor: lm75@48 {
        compatible = "national,lm75";
        reg = <0x48>;  // 7-bit I2C address
        vcc-supply = <&vcc3v3_sys>;  // regulator reference
    };
};
```

### SPI Binding Example

```dts
// SPI controller with two chip selects
spi0: spi@ff1c0000 {
    compatible = "rockchip,rk3399-spi";
    reg = <0x0 0xff1c0000 0x0 0x1000>;
    interrupts = <GIC_SPI 44 IRQ_TYPE_LEVEL_HIGH>;
    clocks = <&clk_spi0>, <&clk_spi0>;
    clock-names = "spi", "pclk";
    
    pinctrl-names = "default";
    pinctrl-0 = <&spi0_clk &spi0_tx &spi0_rx &spi0_cs0>;
    
    #address-cells = <1>;
    #size-cells = <0>;
    
    // SPI device on CS0, mode 0, 10 MHz
    flash: w25q128@0 {
        compatible = "winbond,w25q128", "jedec,spi-nor";
        reg = <0>;  // chip select 0
        spi-max-frequency = <10000000>;
        spi-cpha;   // clock phase = 1 (mode 1)
        // spi-cpol; // uncomment for mode 2/3
    };
};
```

### UART Binding Example

```dts
uart2: serial@ff180000 {
    compatible = "rockchip,rk3399-uart", "snps,dw-apb-uart";
    reg = <0x0 0xff180000 0x0 0x100>;
    interrupts = <GIC_SPI 35 IRQ_TYPE_LEVEL_HIGH>;
    clocks = <&clk_uart2>, <&clk_uart2>;
    clock-names = "baudclk", "apb_pclk";
    
    pinctrl-names = "default";
    pinctrl-0 = <&uart2_xfer>;  // TX/RX pins
    
    reg-shift = <2>;  // 32-bit register stride
    reg-io-width = <4>;  // 32-bit IO access
    dmas = <&dmac 6>, <&dmac 7>;
    dma-names = "tx", "rx";
};
```

### Regulator Binding Example

```dts
// Fixed regulator (always-on 3.3V rail)
vcc3v3_sys: regulator-vcc3v3-sys {
    compatible = "regulator-fixed";
    regulator-name = "vcc3v3_sys";
    regulator-min-microvolt = <3300000>;
    regulator-max-microvolt = <3300000>;
    regulator-always-on;
    regulator-boot-on;
    vin-supply = <&vcc5v0_sys>;  // parent regulator
};

// GPIO-controlled regulator (enable pin)
vcc1v8_cam: regulator-vcc1v8-cam {
    compatible = "regulator-fixed";
    regulator-name = "vcc1v8_cam";
    regulator-min-microvolt = <1800000>;
    regulator-max-microvolt = <1800000>;
    gpio = <&gpio2 RK_PB5 GPIO_ACTIVE_HIGH>;
    enable-active-high;
    startup-delay-us = <10000>;  // 10 ms ramp time
};
```

## Common Pitfalls & Gotchas

1. **Missing `#*-cells` in the controller node** — If the GPIO or interrupt controller node lacks `#gpio-cells` or `#interrupt-cells`, the DT compiler won't error, but the kernel will fail to parse references. Always check that the controller node has these properties.

2. **I2C address format confusion** — The `reg` property in I2C child nodes uses the 7-bit address shifted left by 1 (i.e., the 8-bit write address). A device with 7-bit address 0x48 should be `reg = <0x48>`, not `0x90`. The kernel handles the shift internally.

3. **SPI chip select numbering** — The `reg` value in SPI children corresponds to the chip select line index, not a GPIO number. If your controller has hardware CS0 and CS1, `reg = <0>` selects CS0. Using `reg = <2>` when only two CS lines exist will silently fail.

4. **Regulator supply loops** — If you create a circular `vin-supply` chain (A supplies B, B supplies A), the kernel regulator core will hang during boot. Always verify your supply hierarchy against the schematic.

## Try It Yourself

1. **Add a GPIO-controlled LED** to your board DTS: Create a `gpio-leds` node with `gpios = <&gpioX RK_PXx GPIO_ACTIVE_LOW>` and set `linux,default-trigger = "timer"`. Rebuild and verify the LED blinks.

2. **Add an I2C device** at address 0x76 (common for BME280 sensors). Write the child node with `compatible = "bosch,bme280"` and `reg = <0x76>`. Check `i2cdetect -y <bus>` after boot.

3. **Debug a regulator** by adding `regulator-always-on` to a fixed regulator that's currently off. Use `cat /sys/kernel/debug/regulator/regulator_summary` to verify the supply tree and voltage.

## Next Up

Tomorrow we'll tackle **The `compatible` Property: How Drivers Match DT Nodes** — the critical mechanism that links your hardware description to the kernel driver. We'll explore the matching algorithm, fallback compatibles, and why the order of strings in the property matters more than you think.
