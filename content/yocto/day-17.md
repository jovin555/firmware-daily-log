---
title: "Day 17: U-Boot Recipe: UBOOT_MACHINE & Integration"
date: 2026-06-29
tags: ["til", "yocto", "uboot", "bootloader"]
---

## What I Explored Today

Today I dug into how Yocto builds U-Boot, specifically the `UBOOT_MACHINE` variable and how it controls the entire bootloader build flow. I've been fighting a custom board bring-up where the default U-Boot configuration didn't match our hardware, and understanding this variable was the key to getting a working bootloader image in my `tmp/deploy/images/` directory. The integration between the U-Boot recipe (`u-boot.inc`) and the machine configuration is surprisingly elegant once you see the pattern.

## The Core Concept

U-Boot uses a two-stage build system: configuration then compilation. The configuration step runs `make <config_name>` where `<config_name>` is typically something like `sama5d27_som1_ek_mmc_defconfig`. This generates a `.config` file that drives the entire build. Yocto's `u-boot.inc` recipe wraps this process, but it needs to know which defconfig to use. That's where `UBOOT_MACHINE` comes in.

The variable is set in your machine configuration file (e.g., `meta-custom/conf/machine/myboard.conf`). It directly maps to the defconfig target you'd pass to `make` on a command line. The recipe then calls `oe_runmake -C ${S} ${UBOOT_MACHINE}` during the `do_configure` task. If you get this wrong, you'll either build the wrong board's U-Boot or fail entirely because the defconfig doesn't exist.

The real power is that `UBOOT_MACHINE` is just the entry point. Once set correctly, Yocto handles the rest: it patches the source, configures, compiles, and packages the resulting `u-boot.bin`, `u-boot.img`, or `SPL` into your deploy directory. The recipe also respects `UBOOT_CONFIG` for building multiple configurations (e.g., SD card vs. eMMC boot) in a single build.

## Key Commands / Configuration / Code

**Setting UBOOT_MACHINE in your machine config:**
```bitbake
# meta-custom/conf/machine/myboard.conf
include conf/machine/include/soc-family/my-soc.inc

# This must match a defconfig in U-Boot's configs/ directory
UBOOT_MACHINE = "myboard_defconfig"

# Optional: specify the binary type (default is u-boot.bin)
UBOOT_SUFFIX = "img"
UBOOT_BINARY = "u-boot.${UBOOT_SUFFIX}"

# For SPL (Secondary Program Loader) support
SPL_BINARY = "spl/u-boot-spl.bin"
```

**Verifying the defconfig exists in U-Boot source:**
```bash
# Inside your Yocto build environment
bitbake -c unpack u-boot
ls tmp/work/myboard-poky-linux-gnueabi/u-boot/*/git/configs/myboard_defconfig
# Should return the file path if it exists
```

**Building U-Boot explicitly to test:**
```bash
bitbake u-boot -c cleansstate   # Start fresh
bitbake u-boot                  # Full build
ls tmp/deploy/images/myboard/u-boot*.bin
# Expected output: u-boot-myboard.bin, u-boot.img, etc.
```

**Inspecting the configure task log for debugging:**
```bash
bitbake u-boot -c configure -f
less tmp/work/myboard-poky-linux-gnueabi/u-boot/*/temp/log.do_configure
# Look for: make myboard_defconfig
```

**Using UBOOT_CONFIG for multiple configurations:**
```bitbake
# In machine config
UBOOT_CONFIG = "sd emmc"
UBOOT_CONFIG[sd] = "myboard_sd_defconfig,sd"
UBOOT_CONFIG[emmc] = "myboard_emmc_defconfig,emmc"
UBOOT_MAKE_TARGET = "u-boot.img"
```

## Common Pitfalls & Gotchas

**1. Missing defconfig file**
The most common error: you set `UBOOT_MACHINE = "myboard_defconfig"` but that file doesn't exist in U-Boot's `configs/` directory. The build fails with a cryptic `make: *** No rule to make target 'myboard_defconfig'`. Always verify the defconfig exists after `do_unpack` completes. If you're using a custom U-Boot fork, you need to add the defconfig to your recipe's `SRC_URI` or patch it in.

**2. Case sensitivity and naming conventions**
U-Boot defconfig names follow strict patterns: `soc_board_rev_interface_defconfig`. A mismatch in case (e.g., `MYBOARD_defconfig` vs `myboard_defconfig`) will fail silently during configure. Use `ls configs/*myboard*` in the U-Boot source to find the exact name. Also, some defconfigs use underscores, others hyphens—check the actual file listing.

**3. SPL binary not deployed**
If your board requires SPL (common with TI AM335x, i.MX, or Allwinner SoCs), setting `UBOOT_MACHINE` alone isn't enough. You must also set `SPL_BINARY` in your machine config. Without it, the SPL image won't be copied to the deploy directory, and your board won't boot. Check your SoC's documentation for the exact SPL filename (often `MLO`, `u-boot-spl.bin`, or `SPL`).

## Try It Yourself

1. **Add UBOOT_MACHINE to a custom machine config**: Create a new machine file in `meta-custom/conf/machine/` for a Raspberry Pi 3 (use `rpi_3_defconfig`). Build `u-boot` and verify the binary appears in `tmp/deploy/images/`. Compare the size of `u-boot.bin` vs. the default Raspberry Pi build.

2. **Debug a defconfig mismatch**: Intentionally set `UBOOT_MACHINE` to a non-existent defconfig (e.g., `"nonexistent_defconfig"`), run `bitbake u-boot -c configure`, and examine the error log. Then fix it and rebuild. Note the difference in `log.do_configure` between success and failure.

3. **Implement UBOOT_CONFIG for dual-boot**: If your board supports both SD card and eMMC boot, set up `UBOOT_CONFIG` with two targets. Build both configurations and verify that `tmp/deploy/images/` contains `u-boot-sd.img` and `u-boot-emmc.img` (or similar naming based on your suffix).

## Next up teaser

Tomorrow I'll tackle **devtool: Modify, Build & Deploy Workflows** — the tool that finally makes iterative U-Boot development sane. No more full `bitbake` rebuilds for a one-line patch. We'll walk through modifying U-Boot source, testing changes, and deploying to hardware in under 60 seconds.
