---
title: "Day 08: devfreq: Dynamic Voltage & Frequency Scaling"
date: 2026-06-22
tags: ["til", "power-management", "devfreq", "dvfs", "peripherals"]
---

## What I Explored Today

Today I dug into the Linux `devfreq` framework — the kernel's mechanism for Dynamic Voltage and Frequency Scaling (DVFS) on non-CPU devices. While cpufreq handles DVFS for CPU cores, devfreq manages the same concept for peripherals like GPUs, memory controllers, interconnects, and NPUs. I spent the morning tracing through the governor code and the afternoon testing real DVFS transitions on a development board with a Mali GPU. The key insight: devfreq decouples the *policy* (when to scale) from the *mechanism* (how to scale), using governors and device-specific drivers.

## The Core Concept

DVFS reduces power consumption by lowering voltage and frequency when a device is underutilized, and ramping up when demand increases. The power saved follows the well-known relationship: dynamic power ∝ C × V² × f. Cutting voltage has a quadratic effect, making DVFS the single most impactful power management technique for active peripherals.

The `devfreq` framework provides:
- **Governors**: Policy algorithms (performance, powersave, userspace, simple_ondemand, passive)
- **Device drivers**: Implement the actual frequency/voltage switching via OPP (Operating Performance Points) tables
- **Sysfs interface**: Runtime control and monitoring at `/sys/class/devfreq/`

What makes devfreq tricky is that many peripherals have *shared* voltage domains. For example, a GPU and a memory controller might share a single voltage rail. Scaling one affects the other, which is where the `passive` governor comes in — it allows a device to follow another device's DVFS decisions.

## Key Commands / Configuration / Code

### 1. Checking devfreq devices and current state

```bash
# List all devfreq-managed devices
ls /sys/class/devfreq/

# Check current frequency and governor for a GPU
cat /sys/class/devfreq/ffe40000.gpu/cur_freq
cat /sys/class/devfreq/ffe40000.gpu/governor
cat /sys/class/devfreq/ffe40000.gpu/available_frequencies
cat /sys/class/devfreq/ffe40000.gpu/trans_stat
```

### 2. Changing governor at runtime

```bash
# Switch to performance governor (max freq always)
echo performance > /sys/class/devfreq/ffe40000.gpu/governor

# Switch to simple_ondemand with custom thresholds
echo simple_ondemand > /sys/class/devfreq/ffe40000.gpu/governor
echo 90 > /sys/class/devfreq/ffe40000.gpu/upthreshold
echo 10 > /sys/class/devfreq/ffe40000.gpu/downdifferential
```

### 3. Device tree OPP table example (for a Mali GPU)

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
    opp-600000000 {
        opp-hz = /bits/ 64 <600000000>;
        opp-microvolt = <1050000>;
    };
};
```

### 4. Simple devfreq driver probe snippet (kernel driver)

```c
static int my_devfreq_probe(struct platform_device *pdev)
{
    struct devfreq_simple_ondemand_data *ondemand_data;
    struct devfreq *df;
    struct my_dev *dev = platform_get_drvdata(pdev);

    // Register OPP table from device tree
    dev_pm_opp_of_add_table(&pdev->dev);

    // Initialize devfreq with simple_ondemand governor
    ondemand_data = devm_kzalloc(&pdev->dev, sizeof(*ondemand_data), GFP_KERNEL);
    ondemand_data->upthreshold = 90;
    ondemand_data->downdifferential = 5;

    df = devm_devfreq_add_device(&pdev->dev, &my_devfreq_governor,
                                 ondemand_data);
    if (IS_ERR(df))
        return PTR_ERR(df);

    platform_set_drvdata(pdev, df);
    return 0;
}
```

### 5. Monitoring DVFS transitions live

```bash
# Watch frequency transitions in real time (requires tracepoints)
echo 1 > /sys/kernel/debug/tracing/events/power/devfreq_frequency/enable
cat /sys/kernel/debug/tracing/trace_pipe

# Or use perf
perf stat -e devfreq:devfreq_frequency -a -- sleep 5
```

## Common Pitfalls & Gotchas

**1. Shared voltage domains cause silent failures**
If your GPU and memory controller share a VDD rail, setting the GPU to 600 MHz might force the memory controller to 400 MHz minimum. The kernel won't warn you — you'll just see the memory controller stuck at a higher frequency. Always check `trans_stat` and `cur_freq` on *all* devices in the same power domain after scaling.

**2. OPP tables must match silicon characterization**
Using an OPP that's too aggressive (e.g., 600 MHz at 800 mV) will cause crashes that look like random memory corruption or GPU lockups. The kernel doesn't validate OPPs against your specific chip's speed bin. Always verify OPPs against the manufacturer's datasheet for your specific silicon revision.

**3. The `userspace` governor is not a toy**
Many engineers use `userspace` governor for testing, but forget to set a scaling driver that actually changes voltage. The frequency changes but voltage stays at max — you get no power savings and risk overvolting. Always verify both frequency *and* voltage change:

```bash
# Check voltage rail (if accessible via regulator)
cat /sys/class/regulator/regulator.XXX/microvolts
```

## Try It Yourself

1. **Profile your GPU's DVFS behavior**: Run a GPU benchmark (like `glmark2`) while monitoring `/sys/class/devfreq/*/cur_freq` every 100ms. Plot the frequency over time. Does the governor react fast enough? Try lowering `upthreshold` to 70 and repeat.

2. **Create a custom governor test**: Switch to `userspace` governor and manually step through all available frequencies. At each step, measure power using an INA219 or similar current sensor. Plot power vs. frequency — does it follow the expected quadratic curve?

3. **Debug a shared voltage domain**: On a platform with a Mali GPU and DDR controller, run a memory-intensive workload (like `stress --vm 4`) while monitoring both devfreq devices. Identify if one device's scaling forces the other to a higher frequency. Document the coupling behavior.

## Next Up

Tomorrow: **Regulator Framework: Managing Power Rails in Drivers** — we'll move from frequency scaling to the voltage side of DVFS, exploring how the regulator framework abstracts PMICs, fixed regulators, and switch-mode supplies, and how to properly sequence power rails in your driver probe/remove paths.
