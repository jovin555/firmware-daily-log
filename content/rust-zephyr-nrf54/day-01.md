---
title: "Day 01: nRF54LM20 Overview: Architecture, Cores & Peripherals"
date: 2026-07-10
tags: ["til", "rust-zephyr-nrf54", "nrf54lm20", "architecture"]
---

## What I Explored Today

Today I dove into the nRF54LM20, Nordic's latest multiprotocol SoC that's pushing the boundaries of what's possible in a single-chip wireless design. This chip is a beast: a dual-core Arm Cortex-M33 architecture with a dedicated RISC-V coprocessor, a massive 2 MB flash and 1 MB RAM, and a radio that supports Bluetooth LE, Thread, Matter, and proprietary 2.4 GHz protocols. I spent the morning mapping out the memory map, understanding the core topology, and figuring out how the peripherals are distributed across the two main cores. The goal is to get Rust + Zephyr running on this thing by the end of the week, so today was all about laying the foundation.

## The Core Concept

Why does the nRF54LM20's architecture matter for embedded development? Because you're not just writing code for a single CPU anymore—you're orchestrating a multi-core system where each core has a specific role. The primary Cortex-M33 (the "application core") runs at 128 MHz and handles your main application logic, networking stacks, and complex peripherals. The secondary Cortex-M33 (the "network core") runs at 64 MHz and is dedicated to radio protocol processing—BLE link layer, Thread mesh routing, and so on. There's also a RISC-V coprocessor for ultra-low-power sensor fusion or always-on voice activity detection.

The key insight: you don't have to manage this complexity manually. Zephyr's multi-core support (via the `CONFIG_MP_NUM_CPUS` and `CONFIG_SMP` Kconfig options) abstracts the core topology, but you still need to understand which peripherals are attached to which core's bus. For example, the UARTE instances 0-2 are on the application core's AHB bus, while UARTE 3 is on the network core's bus. If you try to access UARTE3 from the application core without proper IPC, you'll get a hard fault.

The "why" is about power efficiency and real-time guarantees. By offloading radio processing to the network core, the application core can sleep longer, and the network core can meet tight timing requirements for BLE connection intervals (as low as 7.5 ms). The RISC-V coprocessor can handle sensor polling at 1 µA while the rest of the system is in deep sleep.

## Key Commands / Configuration / Code

Let's get practical. Here's how to verify the core topology and memory map using the nRF Connect SDK (NCS) v2.7.0, which is what we'll use with Zephyr.

First, inspect the SoC's device tree from the NCS base:

```bash
# Navigate to the nRF54LM20 DTS file
cd ~/ncs/v2.7.0/zephyr/dts/arm/nordic
cat nrf54lm20.dtsi | head -80
```

You'll see something like:

```dts
/ {
    #address-cells = <2>;
    #size-cells = <2>;
    
    cpus {
        #address-cells = <1>;
        #size-cells = <0>;
        
        cpu0: cpu@0 {
            compatible = "arm,cortex-m33f";
            reg = <0>;
            clock-frequency = <128000000>;
        };
        
        cpu1: cpu@1 {
            compatible = "arm,cortex-m33f";
            reg = <1>;
            clock-frequency = <64000000>;
        };
        
        cpu2: cpu@2 {
            compatible = "riscv";
            reg = <2>;
            clock-frequency = <32000000>;
        };
    };
};
```

Now, let's write a minimal Zephyr application that identifies which core we're on:

```c
// src/main.c
#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

void main(void)
{
    // Zephyr SMP API to get current CPU ID
    unsigned int cpu_id = arch_curr_cpu()->id;
    
    // Get the CPU frequency from DTS
    uint32_t cpu_freq = CONFIG_SYS_CLOCK_HW_CYCLES_PER_SEC;
    
    printk("Booting on CPU%d at %u Hz\n", cpu_id, cpu_freq);
    printk("Flash: %d KB, RAM: %d KB\n", 
           CONFIG_FLASH_SIZE / 1024, 
           CONFIG_SRAM_SIZE / 1024);
    
    // Check which peripherals are available
    if (device_is_ready(DEVICE_DT_GET(DT_NODELABEL(uart0)))) {
        printk("UART0 is ready on this core\n");
    }
    
    while (1) {
        k_sleep(K_SECONDS(1));
    }
}
```

Build for the application core (default):

```bash
west build -b nrf54lm20dk/nrf54lm20/cpuapp -d build_app
west flash -d build_app
```

To build for the network core:

```bash
west build -b nrf54lm20dk/nrf54lm20/cpunet -d build_net
west flash -d build_net
```

The key Kconfig options for multi-core:

```kconfig
# prj.conf for application core
CONFIG_MP_NUM_CPUS=2
CONFIG_SMP=y
CONFIG_SCHED_CPU_MASK=y
CONFIG_SYSTEM_WORKQUEUE_STACK_SIZE=4096
```

## Common Pitfalls & Gotchas

1. **Peripheral bus ownership is not obvious.** The nRF54LM20 has a distributed peripheral bus matrix. Some peripherals (like the Global RTC or the RADIO) are shared between cores, but most are not. If you try to initialize a peripheral from the wrong core without proper IPC, you'll get a bus fault. Always check the peripheral's `reg` property in the DTS—if it's under `cpuapp_peripherals` or `cpunet_peripherals`, it's exclusive to that core.

2. **Flash and RAM are shared, but not equally.** The 2 MB flash and 1 MB RAM are split between cores by default. The application core gets 1.5 MB flash and 768 KB RAM; the network core gets 512 KB flash and 256 KB RAM. You can adjust this via the `nrf54lm20_shared_ram` and `nrf54lm20_shared_flash` partitions in the DTS, but be careful: the network core's radio stack has strict memory requirements.

3. **The RISC-V coprocessor has no Zephyr support yet.** As of NCS v2.7.0, the RISC-V core (cpu2) is not supported by Zephyr's SMP framework. You have to program it separately using Nordic's proprietary IPC mechanism (mailbox + shared memory). Don't try to include it in `CONFIG_MP_NUM_CPUS`—it will break the build.

## Try It Yourself

1. **Map the peripheral bus.** Clone the nRF54LM20 DTS from the NCS and identify which peripherals are under `cpuapp_peripherals` vs `cpunet_peripherals`. List at least 5 peripherals for each core.

2. **Build and run the dual-core hello world.** Create two Zephyr projects: one for the application core and one for the network core. Use the IPC service (nrf_ipc) to send a "Hello from CPU1" message from the network core to the application core, then print it over UART.

3. **Measure core-specific power consumption.** Use the nRF54LM20 DK's built-in current measurement circuit (via the nPM1300 PMIC) to compare idle power consumption when the application core is in WFI vs when both cores are active. Document the difference.

## Next Up

Tomorrow we'll get our hands dirty with **Zephyr on Nordic SoCs: nrfx HAL & Devicetree Overlays**. We'll walk through how Nordic's low-level hardware abstraction layer (nrfx) integrates with Zephyr's devicetree system, how to write custom overlays to enable peripherals not in the default configuration, and why you should almost never call nrfx functions directly from application code.
