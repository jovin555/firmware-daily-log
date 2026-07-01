---
title: "Day 19: Embedded Power Management: Goals, Trade-offs & Standards"
date: 2026-07-01
tags: ["til", "power-management", "power", "standards"]
---

## What I Explored Today

Today I stepped back from specific hardware or kernel internals to map the foundational landscape of embedded power management. I studied the core goals that drive every PM decision—extending battery life, managing thermal budgets, meeting real-time deadlines—and the unavoidable trade-offs between performance, latency, and energy. I also surveyed the key standards (ACPI, Device Tree power domains, PM QoS) that give us a common language across SoCs and boards. This isn't about a single driver or governor; it's about understanding *why* we make the choices we do, and what constraints the standards impose.

## The Core Concept

Embedded power management is fundamentally about *resource allocation under constraint*. The resource is energy (Joules), the constraint is the battery capacity or thermal envelope. Every active cycle of the CPU, every memory access, every peripheral clock tick consumes a discrete amount of energy. The goal is to deliver required performance (throughput, latency) while minimizing wasted energy.

The three primary goals are:
1. **Maximize battery life** – reduce average power draw (P_avg) over time.
2. **Stay within thermal limits** – avoid junction temperatures that cause throttling or damage.
3. **Meet real-time deadlines** – ensure the system wakes and responds fast enough.

These goals conflict. Reducing voltage and frequency (DVFS) saves power but increases execution time. Deep sleep states (suspend-to-RAM) save the most power but have long wake latencies (milliseconds to seconds). The art is in the trade-off: you trade energy for latency, or performance for thermal headroom.

The standards that codify these trade-offs:
- **ACPI (Advanced Configuration and Power Interface)** – defines power states (C-states for CPU, P-states for performance, S-states for system sleep). Common on x86, also used on ARM servers.
- **Device Tree power domains** – on ARM/embedded Linux, the `power-domains` property in the DT binds a device to a power controller that can gate its supply independently.
- **PM QoS (Quality of Service)** – a kernel framework where drivers and applications register latency constraints (e.g., "I need wake-up in under 100 µs") that prevent the system from entering overly deep sleep states.

Understanding these standards means you can read a board's power topology from its DT, predict wake latencies from ACPI tables, and debug why a system won't enter suspend.

## Key Commands / Configuration / Code

### 1. Inspecting C-states and residency (x86/ACPI)
```bash
# Show available C-states and their exit latencies
cat /sys/devices/system/cpu/cpu0/cpuidle/state*/name
cat /sys/devices/system/cpu/cpu0/cpuidle/state*/latency  # microseconds
cat /sys/devices/system/cpu/cpu0/cpuidle/state*/residency # min time to be beneficial

# Example output (Intel NUC):
# state0: "POLL"    latency=0  residency=0
# state1: "C1"      latency=2  residency=2
# state2: "C1E"     latency=10 residency=20
# state3: "C6"      latency=133 residency=300
```
The `residency` field tells you the minimum idle duration before entering that state saves energy (accounting for entry/exit overhead).

### 2. Device Tree power domain binding (ARM)
```dts
/* Example: binding a GPU to a power domain */
&gpu {
    power-domains = <&pmu 0>;   /* phandle to power management unit, domain 0 */
    /* The PMU can now gate the GPU's power rail independently */
};

/* Power controller node */
pmu: power-controller@50000000 {
    compatible = "vendor,power-controller";
    reg = <0x50000000 0x1000>;
    #power-domain-cells = <1>;  /* one cell to specify domain index */
};
```
When the GPU driver idles, the kernel's PM core calls the power controller to turn off the rail. This is how modern SoCs achieve fine-grained power gating.

### 3. PM QoS latency constraints (userspace)
```bash
# Set a CPU wake latency requirement of 50 µs (prevents deep C-states)
echo 50 > /dev/cpu_dma_latency

# Query current constraint
cat /dev/cpu_dma_latency
# Returns the current minimum latency requirement in microseconds
```
This is used by audio drivers (need low latency) or touchscreen controllers. Writing a value blocks C-states with exit latency above that threshold.

## Common Pitfalls & Gotchas

1. **Confusing C-states with P-states.** C-states are idle states (CPU halted, clocks gated, power rail off). P-states are active performance states (voltage/frequency pairs). You can be in P-state 0 (max freq) and still enter C1 (halted). Mixing them up leads to incorrect power analysis.

2. **Device Tree power domains without proper sequencing.** Some power domains require a specific order of enabling/disabling (e.g., turn on memory controller before CPU). If the `power-domains` property lists domains in the wrong order, the SoC may hang or corrupt data. Always check the binding documentation for `power-domain-names` and ordering constraints.

3. **Ignoring PM QoS when debugging suspend.** If a system won't enter deep sleep (e.g., S3 or suspend-to-RAM), the first debug step is to check `/dev/cpu_dma_latency` and `/sys/power/pm_qos_resume_latency_us`. A driver or userspace daemon may have set an unreasonably low latency requirement that blocks all deep states.

## Try It Yourself

1. **Read your platform's idle states.** On any Linux system (x86 or ARM), run `cat /sys/devices/system/cpu/cpu0/cpuidle/state*/{name,latency,residency}`. Identify which state has the highest residency requirement. How long must the CPU be idle to benefit from that state?

2. **Trace power domain toggling on an ARM board.** If you have a BeagleBone Black or Raspberry Pi with mainline kernel, inspect the Device Tree for `power-domains` properties. Use `dtc -I fs -O dts /sys/firmware/devicetree/base` to dump the tree. Find one device that has a power domain and note the phandle.

3. **Test PM QoS impact on C-states.** Write a small C program that opens `/dev/cpu_dma_latency`, writes a low value (e.g., 10), then sleeps for 5 seconds. While it runs, monitor `/sys/devices/system/cpu/cpu0/cpuidle/state3/usage` (or the deepest state) to see that it stops incrementing. Release the FD and watch the counter resume.

## Next Up

Tomorrow I'll dive into the **Linux PM Stack: PM Core, Drivers & Governors** — how the kernel orchestrates idle decisions, what a governor actually does (menu, ladder, TEO), and how drivers register their PM callbacks. We'll trace a suspend-to-idle cycle from userspace to the hardware.
