---
title: "Day 26: devfreq: Dynamic Voltage & Frequency Scaling"
date: 2026-07-08
tags: ["til", "power-management", "devfreq", "dvfs", "peripherals"]
---

## What I Explored Today

Today I dug into the Linux `devfreq` framework — the kernel's mechanism for Dynamic Voltage and Frequency Scaling (DVFS) on non-CPU devices. While cpufreq handles CPU cores, devfreq manages everything else: GPUs, memory controllers, interconnects, and peripheral buses. I traced through the governor logic, tested a real GPU DVFS transition on an i.MX8M Plus, and mapped out how devfreq interacts with the OPP (Operating Performance Points) table and regulator framework. The key insight: devfreq decouples the *policy decision* from the *hardware control*, letting you mix and match governors with device-specific drivers.

## The Core Concept

DVFS exists because dynamic power scales quadratically with voltage and linearly with frequency: `P ∝ C × V² × f`. For peripherals, the workload isn't constant — a GPU rendering a static UI needs far less throughput than one running a game. Devfreq lets you adjust frequency and voltage on-the-fly based on actual utilization.

The framework has three layers:
1. **Devfreq device** — a struct wrapping your hardware, exposing frequency/voltage control via OPP
2. **Governor** — the policy engine that decides the target frequency (e.g., `userspace`, `powersave`, `performance`, `simple_ondemand`)
3. **Core** — the glue that polls utilization, calls the governor, and applies the OPP transition

What makes devfreq powerful is that governors are device-agnostic. The same `simple_ondemand` governor that throttles a Mali GPU can also manage a DDR controller. The device driver just needs to implement `target()` and `get_dev_status()` callbacks.

## Key Commands / Configuration / Code

### Checking Available devfreq Devices

```bash
# List all devfreq devices in sysfs
ls /sys/class/devfreq/

# Typical output on an i.MX8M Plus:
# 5b000000.gpu  5b200000.gpu  5b400000.gpu  5b500000.gpu  ddr

# Check current frequency and governor for GPU0
cat /sys/class/devfreq/5b000000.gpu/cur_freq
cat /sys/class/devfreq/5b000000.gpu/governor
cat /sys/class/devfreq/5b000000.gpu/available_frequencies
```

### Switching Governors at Runtime

```bash
# Switch to powersave (lowest frequency always)
echo powersave > /sys/class/devfreq/5b000000.gpu/governor

# Switch to performance (highest frequency always)
echo performance > /sys/class/devfreq/5b000000.gpu/governor

# Use simple_ondemand with custom polling interval (ms)
echo simple_ondemand > /sys/class/devfreq/5b000000.gpu/governor
echo 50 > /sys/class/devfreq/5b000000.gpu/polling_interval
```

### Minimal devfreq Device Driver Skeleton

```c
#include <linux/devfreq.h>
#include <linux/pm_opp.h>
#include <linux/platform_device.h>

static int my_devfreq_target(struct device *dev, unsigned long *freq, u32 flags)
{
    struct dev_pm_opp *opp;
    unsigned long target_freq;

    // RCU-locked OPP lookup
    opp = devfreq_recommended_opp(dev, freq, flags);
    if (IS_ERR(opp))
        return PTR_ERR(opp);

    target_freq = dev_pm_opp_get_freq(opp);
    dev_pm_opp_put(opp);

    // Hardware-specific frequency switch (e.g., clk_set_rate)
    clk_set_rate(my_clk, target_freq);

    // Regulator voltage update handled by OPP core if registered
    return 0;
}

static int my_devfreq_get_dev_status(struct device *dev,
                                     struct devfreq_dev_status *stat)
{
    // Read hardware utilization counter
    stat->current_frequency = clk_get_rate(my_clk);
    stat->busy_time = readl(UTIL_COUNTER);
    stat->total_time = readl(TOTAL_CYCLES);
    return 0;
}

static struct devfreq_dev_profile my_profile = {
    .polling_ms    = 30,
    .target        = my_devfreq_target,
    .get_dev_status = my_devfreq_get_dev_status,
};

static int my_devfreq_probe(struct platform_device *pdev)
{
    struct device *dev = &pdev->dev;
    struct devfreq *df;

    // Must call dev_pm_opp_of_add_table() first if using DT OPPs
    dev_pm_opp_of_add_table(dev);

    df = devfreq_add_device(dev, &my_profile, "simple_ondemand", NULL);
    if (IS_ERR(df))
        return PTR_ERR(df);

    platform_set_drvdata(pdev, df);
    return 0;
}
```

### Device Tree OPP Table Example

```dts
&gpu {
    operating-points-v2 = <&gpu_opp_table>;
};

gpu_opp_table: opp-table {
    compatible = "operating-points-v2";

    opp-200000000 {
        opp-hz = /bits/ 64 <200000000>;
        opp-microvolt = <800000>;
    };

    opp-400000000 {
        opp-hz = /bits/ 64 <400000000>;
        opp-microvolt = <900000>;
    };

    opp-800000000 {
        opp-hz = /bits/ 64 <800000000>;
        opp-microvolt = <1000000>;
    };
};
```

### Tracing DVFS Transitions

```bash
# Enable devfreq event tracing
echo 1 > /sys/kernel/debug/tracing/events/devfreq/devfreq_monitor/enable
echo 1 > /sys/kernel/debug/tracing/events/devfreq/devfreq_freq_change/enable

# Watch live transitions
cat /sys/kernel/debug/tracing/trace_pipe

# Expected output:
# <idle>-0     [000] ..s. 123.456: devfreq_freq_change: dev=5b000000.gpu freq=400000000
# <idle>-0     [000] ..s. 123.789: devfreq_freq_change: dev=5b000000.gpu freq=200000000
```

## Common Pitfalls & Gotchas

### 1. OPP Table Mismatch with Regulator Constraints
If your OPP table specifies 1.0V but the regulator's `min-microvolt` is 1.1V, the OPP core will silently clamp to 1.1V — and you'll burn extra power. Always verify regulator constraints match your lowest OPP voltage. Use `cat /sys/kernel/debug/regulator/regulator-name/voltage` to check actual output.

### 2. Forgetting to Call `devfreq_recommended_opp()`
Some drivers try to directly call `clk_set_rate()` without consulting the OPP table. This bypasses voltage scaling and can cause instability at high frequencies with low voltage. Always route through `devfreq_recommended_opp()` — it validates the OPP and triggers the regulator update.

### 3. Polling Interval vs. IRQ-Driven Updates
The default `simple_ondemand` governor polls every `polling_ms` milliseconds. For bursty workloads (e.g., GPU frame rendering), this introduces latency. Consider using the `passive` governor with an interrupt-driven `get_dev_status()` callback, or switch to the `tegra_actmon` governor if your hardware has built-in activity monitors.

## Try It Yourself

1. **Profile your GPU's DVFS behavior**: Run `glmark2-es2` while tracing devfreq events. Capture the trace with `trace-cmd record -e devfreq:* glmark2-es2` and analyze how often the GPU transitions between OPPs. Identify if the governor is too aggressive or too slow.

2. **Write a custom userspace governor script**: Create a shell script that reads GPU utilization from `/sys/class/devfreq/*/trans_stat` and manually sets the frequency via `/sys/class/devfreq/*/userspace/set_freq`. Benchmark power consumption with a USB power meter vs. the `ondemand` governor.

3. **Add devfreq support to a simple platform driver**: Take a basic clock-controlled peripheral (e.g., a SPI controller) and add OPP table support in device tree. Implement the `target()` and `get_dev_status()` callbacks, then register it with `devfreq_add_device()`. Verify transitions with trace events.

## Next Up

Tomorrow: **Regulator Framework: Managing Power Rails in Drivers** — we'll dive into the regulator consumer API, voltage negotiation, and how to properly sequence power-up and power-down in your device drivers without frying the hardware.
