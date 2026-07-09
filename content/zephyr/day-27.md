---
title: "Day 27: GDB + OpenOCD: JTAG Debug on Real Hardware"
date: 2026-07-09
tags: ["til", "zephyr", "gdb", "jtag"]
---

## What I Explored Today

After weeks of relying on `printk` and `LOG_*` statements, I finally set up a proper JTAG debugging workflow using GDB and OpenOCD with a Zephyr application running on an STM32F4 Discovery board. The difference between printf-debugging and stepping through real hardware with breakpoints, watchpoints, and live register inspection is night and day. Today I'll walk through the exact setup, commands, and pitfalls I encountered so you can skip the hours I spent fighting toolchain paths and OpenOCD config files.

## The Core Concept

JTAG (Joint Test Action Group) debugging gives you direct, non-intrusive access to the CPU core via a dedicated hardware interface. Unlike semihosting or UART-based debug output, JTAG lets you halt execution, inspect memory, modify registers, and single-step through assembly—all without modifying your application code. OpenOCD acts as the bridge between your host machine's GDB and the target's JTAG/SWD adapter. The key insight: Zephyr's build system generates an ELF file with full DWARF debug symbols, but you must tell GDB where to find the target's memory map and how to handle the reset vector properly. Without this, you'll end up debugging a ghost—GDB thinks it's connected, but every register reads as zero.

## Key Commands / Configuration / Code

### 1. OpenOCD Configuration (stm32f4discovery.cfg)

```tcl
# Minimal OpenOCD config for STM32F4 Discovery with built-in ST-Link/V2
source [find interface/stlink.cfg]
transport select hla_swd
source [find target/stm32f4x.cfg]

# Optional: speed up JTAG clock for faster flashing
adapter speed 4000
```

Launch OpenOCD in a terminal:
```bash
openocd -f board/stm32f4discovery.cfg
```
You should see `Info : stm32f4x.cpu: hardware has 6 breakpoints, 4 watchpoints`.

### 2. GDB Init File (`.gdbinit` in project root)

```gdb
# Connect to OpenOCD's GDB server (port 3333)
target remote localhost:3333

# Reset and halt the target
monitor reset halt

# Load the Zephyr ELF binary
load

# Set a hardware breakpoint at main (Zephyr entry)
hb main

# Continue execution to main
continue
```

### 3. Launching GDB with Zephyr's Toolchain

```bash
# From your build directory (e.g., build/zephyr)
arm-zephyr-eabi-gdb -x ../../.gdbinit zephyr.elf
```

### 4. Useful GDB Commands During a Session

```gdb
# Inspect current PC and stack pointer
info registers pc sp

# Show backtrace (works only if stack is intact)
backtrace

# Read a specific memory address
x/16wx 0x20000000

# Set a watchpoint on a variable (hardware-assisted)
watch my_global_var

# Step one C line (into functions)
step

# Step one assembly instruction
stepi

# Print the value of a Zephyr kernel struct
print k_current_get()

# Dump thread list (requires kernel debug symbols)
thread apply all bt
```

### 5. Debugging a Real Bug: Stack Overflow Detection

```gdb
# Set a hardware watchpoint on the stack guard region
# (Zephyr places a 256-byte guard below each thread stack)
watch *(int*)(_kernel.cpus[0].current->stack_info.start - 4)

# Run until the watchpoint triggers
continue

# When it hits, inspect the corrupted stack frame
backtrace
info registers
```

## Common Pitfalls & Gotchas

### 1. OpenOCD "Error: target not halted" After Flashing
This happens when you try to debug before the target finishes its boot ROM sequence. Always issue `monitor reset halt` *before* `load`. If you forget, the target may be executing code and GDB will fail to write to flash. Fix: restart OpenOCD and GDB, then send `monitor reset halt` immediately.

### 2. GDB Shows "No source file named main.c"
Zephyr's build system places source files in a complex directory tree. If GDB can't find sources, you likely launched it from the wrong directory. Always run GDB from the build directory (e.g., `build/zephyr`). Alternatively, use `directory` command in GDB to add source paths:
```gdb
directory /path/to/zephyr/samples/hello_world/src
```

### 3. Watchpoints Don't Trigger on Global Variables
Zephyr places global variables in `.data` or `.bss` sections that may be in flash (for XIP targets) or RAM. Hardware watchpoints only work on RAM addresses. Verify the variable's address with `info address my_var`. If it's in flash, you need a software watchpoint (much slower) or move the variable to RAM using `__attribute__((section(".ram.data")))`.

## Try It Yourself

1. **Basic Breakpoint Exercise**: Build the `samples/hello_world` for your board, launch OpenOCD, then GDB. Set a breakpoint at `main()`, step through the first three lines, and inspect the value of `printk`'s buffer pointer using `x/s $r0` (ARM calling convention puts first argument in R0).

2. **Stack Overflow Detection**: Modify `samples/philosophers` to reduce the stack size of one thread by 128 bytes. Set a hardware watchpoint on the stack guard region as shown above. Run the application and observe the watchpoint trigger when the thread overflows.

3. **Register-Level Debug**: Flash the `samples/basic/blinky` sample. In GDB, set a breakpoint at the GPIO toggle function. Single-step through the assembly (`stepi`) and watch the `BSRR` register change in the STM32 reference manual. Use `info registers` to confirm the bit pattern matches the expected pin toggle.

## Next Up

Tomorrow we'll dive into **Custom Board Support: DTS & Kconfig**—how to define your own hardware in Device Tree and configure Zephyr's build system to support a custom PCB. We'll walk through creating a minimal board directory, writing a `.dts` file from scratch, and linking it to Kconfig symbols so your drivers actually probe correctly.
