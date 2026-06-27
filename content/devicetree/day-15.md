---
title: "Day 15: Clock Tree in Device Tree: clock-names & clkspec"
date: 2026-06-27
tags: ["til", "devicetree", "clocks", "clkspec", "pll"]
---

## What I Explored Today

Today I dug into how Device Tree models clock trees — specifically how a consumer device requests a specific clock from a provider using `clock-names` and a clock specifier (`clkspec`). I’ve wired up clocks before, but I never fully understood the binding contract between the `clocks` property and the provider’s `#clock-cells`. After tracing through the kernel’s `clk_get()` path and examining real bindings for an i.MX8M Plus, I now see why `clock-names` is not optional for robust drivers, and how the `clkspec` (the cells after the phandle) maps to a specific PLL or divider output.

## The Core Concept

A clock tree in silicon is a directed graph: PLLs generate base frequencies, dividers and muxes transform them, and leaf peripherals consume them. Device Tree represents this with a provider-consumer model.

The provider node declares `#clock-cells` — usually 0 or 1. If `#clock-cells = <0>`, the provider exposes a single clock; the consumer just needs the phandle. If `#clock-cells = <1>`, the provider exposes multiple outputs, and the consumer must supply an additional cell (the clock index or ID) to select which output.

The consumer node uses the `clocks` property, which is a list of phandle + clock-specifier pairs. The `clock-names` property assigns a symbolic name to each entry in `clocks`, in order. The driver then calls `devm_clk_get(dev, "name")` instead of relying on index — this makes the binding self-documenting and order-independent.

Why does this matter? Because clock trees change between SoC revisions. A peripheral might move from PLL2 to PLL3, or a divider gets added. With `clock-names`, the driver doesn’t care about the order in the DT; it asks for "pll" or "div" by name. The DT author can reorder or add clocks without breaking the driver.

## Key Commands / Configuration / Code

Let’s look at a real example from the i.MX8M Plus reference manual. The UART2 peripheral needs two clocks: a baud clock from the audio PLL and an IPG (interface) clock from the system PLL.

**Clock provider snippet (simplified from imx8mp.dtsi):**
```dts
audio_pll1: clock@... {
    compatible = "fsl,imx8m-pll";
    #clock-cells = <1>;          // index 0 = pll out, index 1 = pll bypass?
    clocks = <&osc_24m>;
    clock-names = "pll";
    reg = <0x30380000 0x10000>;
};

clk: clock-controller@30380000 {
    compatible = "fsl,imx8mp-ccm";
    reg = <0x30380000 0x10000>;
    #clock-cells = <1>;          // hundreds of clock IDs defined in dt-bindings
    clocks = <&osc_24m>, <&audio_pll1 0>;
    clock-names = "osc_24m", "audio_pll1";
};
```

**Consumer node (UART2):**
```dts
&uart2 {
    compatible = "fsl,imx8mp-uart", "fsl,imx6q-uart";
    reg = <0x30890000 0x10000>;
    interrupts = <GIC_SPI 28 IRQ_TYPE_LEVEL_HIGH>;
    clocks = <&clk IMX8MP_CLK_UART2>, <&clk IMX8MP_CLK_UART2_ROOT>;
    clock-names = "ipg", "baud";
    status = "disabled";
};
```

Here, `IMX8MP_CLK_UART2` and `IMX8MP_CLK_UART2_ROOT` are integer constants defined in `include/dt-bindings/clock/imx8mp-clock.h`. The driver does:
```c
ipg_clk = devm_clk_get(dev, "ipg");
baud_clk = devm_clk_get(dev, "baud");
```

**Inspecting the clock tree at runtime:**
```bash
# List all clock providers and consumers
find /sys/kernel/debug/clk -name "*.clk_*" -type l 2>/dev/null

# Show a specific clock's tree
cat /sys/kernel/debug/clk/clk_summary | grep uart2

# Trace which driver claimed which clock
cat /sys/kernel/debug/clk/clk_enable_summary | grep uart2
```

**Validating the binding with dt-validate:**
```bash
dt-validate -s /path/to/schemas /path/to/board.dtb
```

## Common Pitfalls & Gotchas

1. **Mismatched `#clock-cells` between provider and consumer**  
   If the provider declares `#clock-cells = <1>` but the consumer only provides a phandle (no extra cell), the kernel will silently fail to parse the clock. The `clk_get()` returns `-EPROBE_DEFER` or an error pointer. Always check the provider’s binding doc.

2. **`clock-names` order must match `clocks` order exactly**  
   The kernel matches names to indices sequentially. If you have three clocks in `clocks` but only two names, or the names are in the wrong order, the driver gets the wrong clock. This is a common copy-paste error when adapting a DTS from another board.

3. **Forgetting that `clock-names` is not required by the DT core, but required by most drivers**  
   The DT spec allows `clock-names` to be absent — the driver can fall back to index-based lookup. However, most modern Linux drivers (especially for complex SoCs) will fail probe if `clock-names` is missing because they use `devm_clk_get(dev, name)` which returns `-ENOENT`. Always include `clock-names` if the driver binding mandates it.

## Try It Yourself

1. **Trace a clock consumer on your target board**  
   Pick a peripheral (e.g., I2C, SPI, UART) and find its `clocks` and `clock-names` in the DTS. Then use `clk_summary` in debugfs to see which parent clocks feed it. Verify the frequency matches the datasheet.

2. **Add a missing clock to a device node**  
   If you have a custom peripheral that needs an additional clock (e.g., a separate baud clock), add a new entry to the `clocks` property and a corresponding name in `clock-names`. Update the driver to call `devm_clk_get()` for the new name. Rebuild and test.

3. **Write a minimal clock provider binding**  
   Create a trivial DT node for a fixed-clock provider with `#clock-cells = <0>` and a consumer that references it. Use `clk_summary` to confirm the consumer claims the clock. Then change `#clock-cells` to `<1>` and add the extra cell — observe the probe failure.

## Next up

Tomorrow we tackle **Interrupt Routing in Device Tree: interrupt-parent**. We’ll trace how a peripheral’s interrupt line travels through interrupt controllers, how `interrupt-parent` resolves the hierarchy, and why you sometimes see it in a child node even when the parent is obvious.
