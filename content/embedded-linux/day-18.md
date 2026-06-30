---
title: "Day 18: MTD Subsystem: NAND, NOR & Flash Layers"
date: 2026-06-30
tags: ["til", "embedded-linux", "mtd", "nand", "flash"]
---

## What I Explored Today

Today I dove into the Linux Memory Technology Device (MTD) subsystem — the kernel layer that abstracts raw flash memory (NAND, NOR, SPI-NOR, and OneNAND) into a uniform interface for upper layers. Unlike block devices (like SATA SSDs) that hide bad-block management and wear-leveling behind a FTL, MTD exposes the raw flash characteristics: erase blocks, OOB (out-of-band) areas, and page-level access. This matters because most embedded systems boot directly from raw flash, and filesystems like JFFS2 and UBIFS rely on MTD's erase-before-write semantics. I spent the day mapping out the MTD stack, probing partitions on a real board, and understanding why `cat /proc/mtd` is your first diagnostic tool.

## The Core Concept

The MTD subsystem exists because flash memory is not a block device. NOR flash allows byte-level reads but requires erase-block-sized (typically 64–128 KiB) erases before writes. NAND flash is page-addressable (2–16 KiB pages) but has inherent bad blocks and requires error correction (ECC). A block device abstraction would hide these details, but that would break filesystems that need to manage erase blocks explicitly.

The MTD stack has three layers:
1. **Hardware drivers** — chip-specific (e.g., `nand_base.c`, `cfi_cmdset_0002.c` for NOR)
2. **MTD core** — provides `mtd_info` structures, partition support (`mtdpart.c`), and character/block device interfaces
3. **Upper layers** — filesystems (JFFS2, UBIFS), flash translation layers (FTL, NFTL), or raw access via `/dev/mtd*`

Key insight: MTD partitions are *not* like disk partitions. They are defined in the kernel (via platform data, device tree, or bootloader) and represent contiguous regions of the flash chip. There is no partition table on the flash itself — the kernel trusts the bootloader or board file.

## Key Commands / Configuration / Code

### Probing MTD from userspace

```bash
# List all MTD devices and partitions
cat /proc/mtd
# Example output:
# dev:    size   erasesize  name
# mtd0: 00100000 00020000 "u-boot"
# mtd1: 00700000 00020000 "kernel"
# mtd2: 0f800000 00020000 "rootfs"

# Get detailed info for mtd0
mtdinfo /dev/mtd0
# Shows: type (nand/nor), eraseblock size, min I/O unit, OOB size

# Dump raw flash content (be careful with writes!)
dd if=/dev/mtd0 of=u-boot.bin bs=1k count=1024
```

### Reading and writing MTD partitions

```bash
# Erase an entire partition (required before write)
flash_erase /dev/mtd1 0 0

# Write a kernel image to mtd1
flashcp zImage /dev/mtd1

# Read OOB data from NAND (first 64 bytes of OOB on page 0)
nanddump -o -p -s 0 -l 64 /dev/mtd2
```

### Device tree binding example (NAND on i.MX6)

```dts
&gpmi_nand {
    pinctrl-names = "default";
    pinctrl-0 = <&pinctrl_gpmi_nand>;
    nand-on-flash-bbt;  /* Use on-flash bad block table */
    status = "okay";

    partition@0 {
        label = "u-boot";
        reg = <0x00000000 0x00200000>;
    };
    partition@1 {
        label = "kernel";
        reg = <0x00200000 0x00800000>;
    };
    partition@2 {
        label = "rootfs";
        reg = <0x00a00000 0x0f600000>;
    };
};
```

### Kernel configuration essentials

```
# Enable MTD core
CONFIG_MTD=y
CONFIG_MTD_CHAR=y          # /dev/mtd* char devices
CONFIG_MTD_BLOCK=y         # /dev/mtdblock* (emulated block, avoid for NAND)

# NAND specific
CONFIG_MTD_NAND=y
CONFIG_MTD_NAND_GPMI=y     # i.MX GPMI controller

# NOR specific
CONFIG_MTD_CFI=y
CONFIG_MTD_CFI_AMDSTD=y    # Common Flash Interface for NOR
```

## Common Pitfalls & Gotchas

1. **Writing without erasing** — On raw flash, you cannot overwrite a page without erasing the entire erase block first. `dd if=file of=/dev/mtd0` will *not* work; use `flashcp` or `flash_erase` + `nandwrite`. The kernel returns EIO if you try to write to a non-erased block.

2. **mtdblock is not a block device** — The `mtdblock` driver emulates a block device on top of MTD, but it has no FTL. Writing to `/dev/mtdblock0` will corrupt your filesystem if you reboot mid-write. Never mount a writable filesystem on mtdblock; use UBIFS or JFFS2 instead.

3. **Bad block handling in NAND** — NAND chips ship with bad blocks. The kernel marks them in the BBT (Bad Block Table). If you erase a partition with `flash_erase`, it preserves the BBT. But if you use `nandwrite` without `-n` (skip BBT check), you may write to a bad block and lose data. Always use `nandwrite -a` to auto-mark bad blocks.

## Try It Yourself

1. **Map your flash layout**: On your embedded board, run `cat /proc/mtd` and `mtdinfo /dev/mtd0`. Identify the erase block size and total size. Compare with the partition table in your device tree or bootloader output.

2. **Dump and verify a partition**: Use `dd if=/dev/mtd0 of=/tmp/backup.bin bs=1k count=16` to dump the first 16 KiB of your bootloader partition. Run `hexdump -C /tmp/backup.bin | head -20` to verify it contains a valid U-Boot header (look for "U-Boot" magic string at offset 0).

3. **Simulate a write cycle (on a test partition only!)**: If you have a spare partition (e.g., a "data" partition), erase it with `flash_erase /dev/mtd3 0 0`, then write a small file with `nandwrite -p /dev/mtd3 test.bin`. Verify with `nanddump /dev/mtd3`. Then erase again and confirm the data is gone.

## Next Up

Tomorrow I'll dive into **Embedded Filesystems: JFFS2, UBIFS, SquashFS** — how these filesystems handle wear-leveling, compression, and power-loss recovery on raw MTD devices. We'll compare JFFS2's garbage collection overhead with UBIFS's log-structured design, and see why SquashFS is the go-to for read-only root filesystems.
