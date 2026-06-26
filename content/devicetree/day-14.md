---
title: "Day 14: Pinmux & Pincontrol: Configuring Pin Functions via DT"
date: 2026-06-26
tags: ["til", "devicetree", "pinmux", "pincontrol", "iomux"]
---

## What I Explored Today

Today I dug into the Device Tree `pinctrl` subsystem — the mechanism that tells the SoC which physical pins get which electrical function. On a modern i.MX or STM32MP1 board, a single GPIO pad can serve as UART TX, I2C SDA, PWM output, or a general-purpose input. The pinmux controller in the kernel reads DT bindings to configure these muxes at boot and during runtime power management. I traced through the `pinctrl-single` driver on a TI AM335x and the `pinctrl-imx` driver on an i.MX8M Mini to see how `pinctrl-0`, `pinctrl-names`, and the pin configuration nodes actually get parsed.

## The Core Concept

Pinmux (pin multiplexing) and pincontrol are two sides of the same coin. The mux selects which peripheral signal is routed to a physical pad. The pincontrol configures the pad's electrical properties: drive strength, pull-up/down, slew rate, and schmitt trigger. In DT, these are combined into a single `pinctrl-*` property that a device node references.

Why does this matter? Without correct pinmux, your UART TX pin might be routing the PWM signal instead — silent failure, no data. Without correct pincontrol, your high-speed SDIO interface might glitch due to improper drive strength or missing pull-ups. The kernel's pinctrl framework handles this at probe time: when a driver calls `pinctrl_bind_pins()`, the framework walks the `pinctrl-0` phandles, resolves them to the pin controller node, and programs the hardware registers.

The key insight: pinmux is a *resource allocation* problem. Two devices cannot claim the same physical pin for different functions. The pinctrl subsystem enforces this exclusivity, returning `-EBUSY` if a pin is already claimed. This is why you see `pinctrl-0` and `pinctrl-1` for "default" and "sleep" states — the kernel can reconfigure pins when entering low-power modes, freeing them for other uses.

## Key Commands / Configuration / Code

### Basic pinctrl binding for an I2C controller (i.MX8M Mini)

```dts
&i2c2 {
    pinctrl-names = "default", "sleep";
    pinctrl-0 = <&pinctrl_i2c2>;
    pinctrl-1 = <&pinctrl_i2c2_sleep>;
    status = "okay";
};

&iomuxc {
    pinctrl_i2c2: i2c2grp {
        fsl,pins = <
            MX8MM_IOMUXC_I2C2_SCL_I2C2_SCL    0x400001c2
            MX8MM_IOMUXC_I2C2_SDA_I2C2_SDA    0x400001c2
        >;
    };

    pinctrl_i2c2_sleep: i2c2grp-sleep {
        fsl,pins = <
            MX8MM_IOMUXC_I2C2_SCL_GPIO5_IO16  0x1c0  /* input, pull-up */
            MX8MM_IOMUXC_I2C2_SDA_GPIO5_IO17  0x1c0
        >;
    };
};
```

The `fsl,pins` macro encodes: the pad name, the mux mode (e.g., `I2C2_SCL`), and a 32-bit configuration value. The config value `0x400001c2` on i.MX means: 100k pull-up enabled, hysteresis on, slew rate fast, drive strength R0/6 (medium). The sleep state reconfigures the same pads as GPIO inputs with pull-ups — safe for power-off.

### Generic pinctrl-single binding (TI AM335x)

```dts
&am33xx_pinmux {
    uart0_pins: uart0-pins {
        pinctrl-single,pins = <
            0x170 (PIN_INPUT | MUX_MODE0)  /* UART0_RXD */
            0x174 (PIN_OUTPUT | MUX_MODE0) /* UART0_TXD */
        >;
    };
};

&uart0 {
    pinctrl-names = "default";
    pinctrl-0 = <&uart0_pins>;
};
```

Here `0x170` and `0x174` are register offsets from the pinmux base. The second cell is a bitfield: bits 0-5 select mux mode, bits 6-7 set input/output, bits 8-15 control pull-up/down. The `pinctrl-single` driver reads these raw register values and writes them directly.

### Debugging pinmux at runtime

```bash
# List all pin controllers and their claimed pins
cat /sys/kernel/debug/pinctrl/pinctrl-handles

# Show pin state for a specific device
cat /sys/kernel/debug/pinctrl/2000000.iomuxc/pinmux-pins

# Dump current mux configuration for a specific pad
cat /sys/kernel/debug/gpio | grep GPIO1_IO03
```

## Common Pitfalls & Gotchas

1. **Missing `pinctrl-names` causes silent probe failure**  
   The kernel expects `pinctrl-names` to match the index of `pinctrl-*` properties. If you have `pinctrl-0` but no `pinctrl-names`, the pinctrl core still applies the default state, but any `pinctrl_select_state()` call in the driver will fail. Always include at least `pinctrl-names = "default"`.

2. **Pin conflicts between kernel and bootloader**  
   U-Boot often configures pins for early console or MMC boot. If the kernel's pinctrl driver tries to reconfigure a pin that the bootloader left in a different mux mode, you can get glitches or lockups. Solution: use `pinctrl-0` with the exact same configuration as the bootloader, or add a `bootph-all` property to the pin node to share the config.

3. **Drive strength values are SoC-specific and not portable**  
   The `0x400001c2` magic number on i.MX means something completely different on STM32MP1 or Rockchip. Always consult the SoC reference manual's IOMUX chapter for the bit layout. Copying a config from a different board will either do nothing or fry the pad.

## Try It Yourself

1. **Decode a pin config value**: On your target board, pick a pin node from the DT, look up the SoC manual's IOMUX control register description, and manually decode the drive strength, pull type, and slew rate from the hex value. Verify against the schematic.

2. **Add a sleep state**: Take an existing device node (e.g., SPI or UART) that has only `pinctrl-0`. Add a `pinctrl-1` sleep state that reconfigures the pins as GPIO inputs with pull-downs. Test by entering suspend (`echo mem > /sys/power/state`) and checking the pin voltage with a multimeter.

3. **Debug a pin conflict**: Write a kernel module that requests a GPIO on a pin already claimed by pinctrl. Observe the `-EBUSY` error in `dmesg`. Then use the debugfs `pinmux-pins` file to find which driver owns the pin.

## Next Up

Tomorrow: **Clock Tree in Device Tree: clock-names & clkspec** — how to wire up PLLs, dividers, and gates using `clocks`, `clock-names`, and the `#clock-cells` phandle mechanism, plus debugging clock tree issues with `clk_summary`.
