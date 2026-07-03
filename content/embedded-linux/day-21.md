---
title: "Day 21: GDB Cross-Debug: JTAG, gdbserver & Remote Debug"
date: 2026-07-03
tags: ["til", "embedded-linux", "gdb", "jtag"]
---

## What I Explored Today

Today I dove into the three dominant approaches for remote debugging embedded Linux targets: JTAG-based hardware debugging, gdbserver over network/serial, and the GDB remote stub protocol. While I've used GDB locally for years, cross-debugging introduces a whole new layer of complexity—different architectures, transport layers, and the fundamental challenge of debugging code that isn't running on your host machine. I set up all three methods against a BeagleBone Black target (ARM Cortex-A8) and a QEMU ARM virtual machine to understand the tradeoffs.

## The Core Concept

Remote debugging on embedded Linux isn't just about running GDB on a different machine—it's about bridging the gap between your development host (x86_64, running a full IDE) and your target (ARM, RISC-V, or MIPS, often headless and resource-constrained). The core problem: the debugger needs to control execution, read/write memory, and inspect registers on a CPU it doesn't run on.

Three solutions exist, each with different levels of invasiveness and capability:

1. **JTAG/SWD debugging**: A hardware debug probe (J-Link, OpenOCD with FTDI, Segger) connects to the target's JTAG or SWD pins. The probe speaks to the CPU's debug interface directly—no OS required. You can debug bootloaders, kernel early boot, and even halt the CPU at any point. This is the most powerful but requires physical access and a probe ($50–$5000).

2. **gdbserver**: A lightweight stub runs *on the target* (compiled for the target architecture). It listens on a TCP port or serial line. Your host GDB (cross-compiled for the target) connects to it. gdbserver uses Linux's `ptrace()` syscall to control the target process. No special hardware needed, but the target must be running Linux and the process must be debuggable.

3. **GDB remote stub**: The lowest-level software approach. You embed a small GDB remote protocol handler directly into your firmware or bare-metal code. The stub handles breakpoints, single-stepping, and memory access via a serial or network transport. Common in RTOS and bare-metal development.

The key insight: all three speak the *same* GDB Remote Serial Protocol (RSP) on the wire. The difference is what sits at the other end—a hardware probe, an OS-based stub, or your own code.

## Key Commands / Configuration / Code

### 1. JTAG with OpenOCD + GDB

```bash
# Start OpenOCD with FTDI-based JTAG adapter targeting AM335x
openocd -f interface/ftdi/olimex-arm-usb-tiny-h.cfg \
        -f target/am335x.cfg \
        -c "gdb_port 3333" \
        -c "telnet_port 4444"

# In another terminal, start cross-GDB (ARM target)
arm-linux-gnueabihf-gdb vmlinux

# Inside GDB, connect to OpenOCD's GDB server
(gdb) target remote :3333
(gdb) monitor reset halt          # Halt CPU via JTAG
(gdb) monitor flash write_image u-boot.bin 0x08000000
(gdb) load                         # Load symbols
(gdb) break start_kernel
(gdb) continue
```

### 2. gdbserver over Ethernet

```bash
# On target (BeagleBone Black, ARM)
# Install gdbserver (part of gdb package for target)
gdbserver :2345 /usr/bin/my_application

# On host (x86_64)
# Use cross-compiled GDB for ARM
arm-linux-gnueabihf-gdb my_application
(gdb) target remote 192.168.1.100:2345
(gdb) break main
(gdb) continue
```

### 3. gdbserver attaching to a running process

```bash
# On target, attach to PID 1234
gdbserver --attach :2345 1234

# On host, same connection as above
(gdb) target remote 192.168.1.100:2345
(gdb) info threads
(gdb) thread 2
(gdb) backtrace
```

### 4. Minimal GDB remote stub (conceptual)

```c
// Pseudocode for a bare-metal stub
void gdb_stub_loop(void) {
    unsigned char packet[512];
    while (1) {
        uart_read(packet);                    // Read '$' packet
        switch (packet[1]) {
            case 'g':                         // Read registers
                send_registers_to_host();
                break;
            case 'G':                         // Write registers
                write_registers_from_host(packet);
                break;
            case 'm':                         // Read memory
                addr = parse_addr(packet);
                len  = parse_len(packet);
                send_memory(addr, len);
                break;
            case 'c':                         // Continue execution
                return;                       // Exit stub, run app
        }
    }
}
```

## Common Pitfalls & Gotchas

1. **Architecture mismatch in GDB**: The single most common mistake. You *must* use a GDB compiled for the *host* architecture (x86_64) but with *target* support for the remote CPU. Running `gdb-multiarch` on your host and connecting to an ARM target works. Running `arm-linux-gnueabihf-gdb` on an ARM target (if it even exists) is wrong—you want the debugger on your powerful host, not the constrained target.

2. **JTAG voltage and signal integrity**: Many JTAG probes are 3.3V, but some older targets (or FPGAs) use 1.8V or 5V. Connecting a 3.3V probe to a 1.8V JTAG port can damage the target. Always check the target's JTAG voltage and use a level shifter if needed. Also, long wires (>15cm) cause signal reflections—keep JTAG lines short and consider 10-22 ohm series resistors.

3. **gdbserver and ASLR**: Modern Linux distributions enable ASLR (Address Space Layout Randomization). When you attach gdbserver to a running process, the addresses you see in GDB are *after* ASLR relocation. If you set breakpoints by symbol before connecting, they'll fail. Solution: either disable ASLR (`echo 0 > /proc/sys/kernel/randomize_va_space`) or use hardware breakpoints via the `hbreak` command.

4. **SIGTRAP vs breakpoints**: When you set a software breakpoint, GDB writes a trap instruction (`0xE7F001F0` on ARM) into the instruction stream. If the target's flash is write-protected or the code is in XIP (eXecute In Place) memory, this write fails silently. Use `hbreak` for hardware breakpoints in flash/ROM, or ensure the memory region is writable.

## Try It Yourself

1. **Set up gdbserver on a Raspberry Pi**: Cross-compile a simple "hello world" with `arm-linux-gnueabihf-gcc -g -o hello hello.c`. Copy it to the Pi. Run `gdbserver :2345 ./hello` on the Pi, then connect from your host with `arm-linux-gnueabihf-gdb hello` and `target remote <pi-ip>:2345`. Step through `main()` and inspect local variables.

2. **JTAG halt and inspect**: If you have a JTAG probe (or use QEMU with `-s -S`), connect GDB to a running Linux kernel. Use `monitor reset halt` to stop the CPU at the reset vector. Examine the program counter and stack pointer. Set a breakpoint at `start_kernel` and continue—watch the kernel boot under debugger control.

3. **Debug a segfault remotely**: Write a C program that dereferences a NULL pointer. Compile with `-g -O0`. Run it under gdbserver (`gdbserver :2345 ./crash`). Connect GDB, set `handle SIGSEGV stop`, and continue. When it crashes, use `backtrace`, `info registers`, and `x/10i $pc-20` to examine the faulting instruction and call stack.

## Next Up

Tomorrow: **ftrace & trace-cmd: Function & Latency Tracing**. We'll move from breakpoint-based debugging to zero-overhead kernel tracing—tracing every function call, measuring IRQ latency, and using trace-cmd to capture and visualize kernel behavior without halting execution.
