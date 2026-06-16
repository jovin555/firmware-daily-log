---
title: "Day 04: U-Boot Environment: Variables, Commands & Scripting"
date: 2026-06-16
tags: ["til", "embedded-linux", "uboot", "environment"]
---

## What I Explored Today

Today I dove deep into the U-Boot environment — the persistent key-value store that controls boot behavior, from kernel command lines to boot scripts. I spent time understanding how variables like `bootargs`, `bootcmd`, and `loadaddr` form the backbone of every embedded Linux boot sequence. I also experimented with U-Boot's scripting capabilities, which allow conditional logic, loops, and even function-like constructs using the Hush shell. The environment is stored in a dedicated partition (usually on SPI flash, eMMC, or SD card), and corrupting it can brick a board — so I also looked at recovery mechanisms like the redundant environment and `env default -f -a`.

## The Core Concept

The U-Boot environment is the bootloader's persistent configuration layer. It bridges the gap between hardware initialization and kernel handoff. Why does this matter? Because without it, you'd have to recompile U-Boot for every kernel command-line change, device tree tweak, or boot device swap. The environment stores variables as plain text (e.g., `bootdelay=3`, `bootargs=console=ttymxc0,115200 root=/dev/mmcblk0p2`), and U-Boot evaluates them at boot time. The real power comes from scripting: you can chain commands, check return values, and even implement fallback boot logic. The environment is typically stored in a fixed-size region (e.g., 128KB) with a CRC32 checksum for integrity. A redundant copy (e.g., `env_redund`) provides failover if the primary gets corrupted.

## Key Commands / Configuration / Code

### Inspecting and Modifying Variables

```bash
# Print all environment variables
U-Boot> printenv

# Print a specific variable
U-Boot> printenv bootargs

# Set a variable (persistent after save)
U-Boot> setenv bootargs 'console=ttymxc0,115200 root=/dev/mmcblk0p2 rootwait rw'

# Delete a variable
U-Boot> setenv useless_var

# Save to persistent storage (e.g., SPI flash, eMMC)
U-Boot> saveenv

# Load default environment (factory reset)
U-Boot> env default -f -a
U-Boot> saveenv
```

### Boot Flow Variables

```bash
# Typical bootcmd: the script that runs automatically
U-Boot> setenv bootcmd 'mmc dev 0; ext4load mmc 0:2 ${loadaddr} /boot/zImage; ext4load mmc 0:2 ${fdt_addr_r} /boot/board.dtb; bootz ${loadaddr} - ${fdt_addr_r}'

# bootdelay: seconds to wait before executing bootcmd
U-Boot> setenv bootdelay 2

# bootargs: kernel command line
U-Boot> setenv bootargs 'console=ttyS0,115200 root=/dev/mmcblk0p2 rootfstype=ext4 rw'
```

### Scripting with Hush Shell

```bash
# Simple conditional: check if variable exists
U-Boot> if test -n "${bootargs}"; then echo "bootargs is set"; else echo "bootargs is empty"; fi

# Loop example: boot from multiple MMC partitions
U-Boot> setenv boot_try 'for part in 1 2 3; do if mmc dev 0 && ext4load mmc 0:${part} ${loadaddr} /boot/zImage; then echo "Boot from partition ${part}"; bootz ${loadaddr}; fi; done; echo "No valid kernel found"'

# Function-like construct using setexpr
U-Boot> setenv myfunc 'echo "Hello from myfunc"; setexpr count ${count} + 1'
U-Boot> setenv count 0
U-Boot> run myfunc
U-Boot> echo ${count}
1
```

### Environment Storage Layout (for reference)

```c
// From include/env_default.h (simplified)
struct environment_s {
    uint32_t    crc;            // CRC32 of data
    unsigned char data[ENV_SIZE]; // Variable data (key=value\0 pairs)
};

// Default environment size: 0x20000 (128KB) on many platforms
// Redundant environment at offset +0x20000
```

## Common Pitfalls & Gotchas

1. **Corrupt environment bricks the board.** If the CRC32 check fails, U-Boot falls back to the default environment, but if both primary and redundant copies are corrupt, the board may hang. Always keep a backup of your working environment (`saveenv` before risky changes). Recovery often requires re-flashing via JTAG or SD card.

2. **Variable expansion in strings is tricky.** U-Boot's Hush shell expands `${varname}` at parse time, not at runtime. If you set a variable containing `${othervar}`, it will be expanded immediately. Use `setenv` with single quotes or escape with `\$` to defer expansion. Example: `setenv myvar '${bootargs} extra=debug'` stores the literal string `${bootargs} extra=debug`, which expands later when `run myvar` executes.

3. **`saveenv` writes to the wrong device.** If you have multiple storage devices (e.g., SPI flash and eMMC), `saveenv` writes to the device selected by `env_device` or the hardware default. Always verify with `printenv` after save. Use `env info` to check which device is active.

## Try It Yourself

1. **Create a fallback boot script.** Write a `bootcmd` that tries to load a kernel from MMC partition 2, then falls back to partition 3, and finally to TFTP if both fail. Use `if`, `else`, and `tftp` commands. Save it and test by temporarily corrupting partition 2's kernel.

2. **Implement a boot counter.** Use `setexpr` to increment a counter variable each time the board boots. If the counter exceeds 3, run `env default -f -a` to reset to factory defaults. This is useful for recovery after repeated failed boots.

3. **Debug a variable expansion issue.** Set `bootargs` to `console=ttyS0,115200 root=/dev/mmcblk0p2` and then create a variable `myargs` that contains `${bootargs} debug`. Print `myargs` and verify it expands correctly. Then try to set `myargs` with double quotes and observe the difference.

## Next Up

Tomorrow, I'll dive into **Kernel Configuration: menuconfig, defconfig & Fragments** — how to efficiently manage kernel build options across multiple boards, using `menuconfig` for interactive tweaks, `defconfig` for baseline configs, and config fragments for modular overlays.
