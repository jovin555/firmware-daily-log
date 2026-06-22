---
title: "Day 10: Clock Gating & Power Domains"
date: 2026-06-22
tags: ["til", "power-management", "clock-gating", "power-domains"]
---

## What I Explored Today

Today I dug into two of the most fundamental hardware-level power-saving techniques: clock gating and power domains. While they sound similar, they operate at completely different levels of the power management stack. Clock gating stops the toggling of clock signals to idle logic blocks, saving dynamic power. Power domains go further—they physically isolate and shut off voltage to entire sections of the chip, eliminating both dynamic and static (leakage) power. I spent the day tracing through a reference implementation on an STM32U5 MCU and a Zynq-7000 SoC, mapping out how these techniques interact with the Linux kernel's runtime PM framework.

## The Core Concept

The key insight is that clock gating and power domains solve different problems, and you need both. Clock gating is cheap, fast, and fine-grained—it can turn off a peripheral's clock in a few cycles. But it only saves dynamic power (P ∝ CV²f). The moment the clock stops, the switching power goes to zero, but leakage current still flows through every transistor. On modern deep-submicron processes (28nm and below), leakage can account for 30-50% of total power in idle blocks.

Power domains solve leakage. By using header or footer switches (usually PMOS or NMOS transistors acting as power gates), you can disconnect an entire voltage island from the main supply rail. This is called power gating. The trade-off is latency: entering and exiting a power domain takes microseconds to milliseconds because you must sequence the power rail, wait for stabilization, and restore state if retention flip-flops are used.

The real art is deciding what goes in which domain. Critical path logic (PLLs, always-on timers, wake-up controllers) stays in the "always-on" domain. Everything else gets partitioned into switchable domains. The Linux kernel exposes this via the `struct generic_pm_domain` (genpd) framework, which coordinates clock gating, power gating, and runtime PM callbacks in the correct sequence.

## Key Commands / Configuration / Code

### 1. Checking Clock Gating Status on Linux (i.MX8M)

```bash
# List all clocks and their enable/disable state
cat /sys/kernel/debug/clk/clk_summary | head -30

# Example output fragment:
#   clock                    enable_cnt  prepare_cnt  rate        accuracy   phase
# -------------------------------------------------------------------------------
#  osc_24m                          5            5    24000000          0 0
#  uart1_clk                        1            1    80000000          0 0
#  uart2_clk                        0            0    80000000          0 0
#  usdhc1_clk                       1            1    200000000         0 0
```

If `enable_cnt` is 0, the clock is gated. The CCF (Common Clock Framework) handles this automatically when the driver calls `clk_disable_unprepare()`.

### 2. Power Domain Control via sysfs (Zynq-7000)

```bash
# List available power domains
ls -d /sys/devices/platform/*/power_domain*

# Check current state of a specific domain
cat /sys/devices/platform/f8000000.slcr/power/control
# Output: on  (or "auto" if runtime PM is managing it)

# Force a domain off (for testing)
echo off > /sys/devices/platform/f8000000.slcr/power/control
```

### 3. Device Tree Binding for Power Domains (STM32MP1)

```dts
// arch/arm/boot/dts/stm32mp151.dtsi
// Defines a power domain for the GPU
gpu: gpu@59000000 {
    compatible = "vivante,gc";
    reg = <0x59000000 0x800>;
    clocks = <&rcc GPU_CLK>, <&rcc GPU_K_CLK>;
    clock-names = "core", "kernel";
    resets = <&rcc GPU_RST>;
    // Bind to the power domain controller
    power-domains = <&pd_gpu>;
    status = "disabled";
};

// The power domain controller itself
pd_gpu: pd_gpu@... {
    compatible = "st,stm32mp1-power-domain";
    #power-domain-cells = <0>;
    domain-id = <PD_GPU>;
    // Voltage regulator for this domain
    vdd-supply = <&vdd_gpu>;
};
```

### 4. Kernel Driver Integration (Simplified genpd Callback)

```c
// From drivers/base/power/domain.c (conceptual)
static int gpu_power_on(struct generic_pm_domain *genpd)
{
    // 1. Enable the voltage regulator
    regulator_enable(genpd->regulator);
    
    // 2. Wait for power rail to stabilize (datasheet-specific delay)
    udelay(100);
    
    // 3. Enable the domain's main clock
    clk_enable(genpd->clk);
    
    // 4. Release reset (if applicable)
    reset_control_deassert(genpd->reset);
    
    return 0;
}
```

## Common Pitfalls & Gotchas

**1. Sequencing Violations Cause Silent Data Corruption**
The biggest trap: turning on a power domain before its clock is stable, or gating a clock while the domain is transitioning. This can cause latch-up or metastability. Always follow the exact power-up sequence from the datasheet: voltage → clock → reset deassert → functional clock. The genpd framework enforces this, but custom drivers often skip steps.

**2. Retention vs. Non-Retention Flip-Flops**
When a power domain shuts off, all registers in that domain lose state unless they are in a retention register (backed by a always-on supply). Engineers frequently forget to mark critical registers (like FIFO pointers or DMA descriptors) as retention. Result: the peripheral comes back in an undefined state. Always check the RTL or reference manual for retention cell placement.

**3. Clock Gating Doesn't Help with Leakage**
I've seen teams spend weeks optimizing clock gating for a peripheral that's 90% leakage-dominated. On a 28nm chip, a USB controller with its clock gated still leaks ~5mW. The only fix is power gating. Profile first: measure dynamic vs. static power with a precision shunt resistor or on-chip power monitor before deciding which technique to apply.

## Try It Yourself

1. **Inspect clock gating on your target**: Run `cat /sys/kernel/debug/clk/clk_summary` and identify three peripherals with `enable_cnt = 0`. Cross-reference with `lsof` or `lsmod` to confirm the driver is unloaded. This is your baseline for clock gating coverage.

2. **Map power domains from the device tree**: On a supported SoC (i.MX8M, STM32MP1, or Zynq), run `dtc -I dtb -O dts /sys/firmware/fdt | grep power-domains` and list every peripheral bound to a power domain. Check if any critical peripherals (like the UART console) are in a switchable domain—if so, test what happens when you suspend it.

3. **Measure the latency of a power domain transition**: Write a small kernel module that calls `pm_runtime_get_sync()` and `pm_runtime_put_sync()` on a GPU or VPU device, and measure the time with `ktime_get()`. Compare to the datasheet's stated power-up time. If it's significantly longer, you likely have a clock or regulator settling delay that can be optimized.

## Next Up

Tomorrow we move from hardware-level techniques to system-level profiling. We'll fire up `powertop` and learn how to identify which processes, drivers, and interrupts are preventing your system from reaching deep idle states. You'll learn to read the "wakeup" statistics and track down the real power hogs in a running Linux system.
