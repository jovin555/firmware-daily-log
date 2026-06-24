---
title: "Day 12: TF-A BL1, BL2, BL3: Each Stage Explained"
date: 2026-06-24
tags: ["til", "trustzone", "bl1", "bl2", "bl3"]
---

## What I Explored Today

I spent the day tracing the boot flow through TF-A’s three boot loader stages: BL1, BL2, and BL3. While the TF-A documentation covers each stage in isolation, I wanted to understand how they chain together in practice—specifically how BL1 hands off to BL2, and how BL2 stages BL3 (BL31, BL32, BL33) in memory before jumping. I built a minimal FVP (Fixed Virtual Platform) configuration, instrumented each stage with `INFO` logs, and verified the memory layout using the `memmap` tool. The key insight: each stage has a strict privilege level, memory carve-out, and handoff contract that, if violated, causes a silent hang or a panic in `plat_panic_handler`.

## The Core Concept

Why three stages? Because the boot process must transition from the most trusted, immutable code (BL1, in on-chip ROM) to the rich OS (BL33, typically U-Boot or UEFI) while maintaining the chain of trust. Each stage has a specific responsibility:

- **BL1 (Boot Loader Stage 1)**: The first code executed after reset. It runs from on-chip SRAM or ROM, sets up the initial MMU with a flat map, configures the DRAM controller, and loads BL2 from a predefined storage location (e.g., eMMC, NOR flash). BL1 is the root of trust—it must be immutable and authenticated.
- **BL2 (Boot Loader Stage 2)**: Runs from DRAM, with elevated privileges (S-EL1). Its job is to load and authenticate the remaining images: BL31 (EL3 runtime firmware), BL32 (Trusted OS, e.g., OP-TEE), and BL33 (non-secure bootloader). BL2 also sets up the memory layout and passes a `bl31_params` structure to BL31.
- **BL3 (Boot Loader Stage 3)**: Actually three sub-stages: BL31 (EL3 monitor), BL32 (S-EL1 Trusted OS), and BL33 (EL2/EL1 non-secure). BL31 handles SMC calls and PSCI; BL32 runs trusted applications; BL33 boots Linux or another OS.

The critical design choice: BL1 and BL2 are ephemeral—they execute and then are either overwritten or left dormant. BL31 persists in memory to handle secure monitor calls.

## Key Commands / Configuration / Code

### 1. Building TF-A with BL1, BL2, and BL31 for FVP

```bash
# Clone TF-A (tag v2.10)
git clone https://git.trustedfirmware.org/TF-A/trusted-firmware-a.git
cd trusted-firmware-a

# Build for FVP_Base_RevC-2xAEMvA with debug enabled
make PLAT=fvp DEBUG=1 LOG_LEVEL=50 \
    BL33=/path/to/u-boot.bin \
    all fip

# Output files:
# build/fvp/debug/bl1.bin
# build/fvp/debug/bl2.bin
# build/fvp/debug/bl31.bin
# build/fvp/debug/fip.bin
```

The `LOG_LEVEL=50` enables verbose debug output from all stages. The `fip` target creates a FIP (Firmware Image Package) containing BL2, BL31, BL32 (if present), and BL33. BL1 is separate because it must be placed in ROM.

### 2. Memory Layout Verification

```bash
# Generate memory map for BL2
make PLAT=fvp DEBUG=1 MEM_MAP_GEN=1 bl2

# View the generated map
cat build/fvp/debug/bl2.memmap
```

Example output (trimmed):
```
Memory map for 'bl2' (xlat_tables v2):
  Region 0: 0x04001000 - 0x04002000 (4 KB)  : Code (RO)
  Region 1: 0x04002000 - 0x04003000 (4 KB)  : RO data
  Region 2: 0x04003000 - 0x04005000 (8 KB)  : RW data
  Region 3: 0x04005000 - 0x04006000 (4 KB)  : BSS
```

This confirms BL2’s memory footprint. If BL2 exceeds its allocated region (defined in `plat/fvp/include/platform_def.h`), the build fails with a linker error.

### 3. BL1 to BL2 Handoff Code (Simplified)

In `bl1/bl1_main.c`, the handoff happens via `bl1_run_bl2()`:

```c
/*******************************************************************************
 * BL1 hands over to BL2 at the entry point address
 ******************************************************************************/
void bl1_run_bl2(entry_point_info_t *bl2_ep)
{
    /* Ensure MMU and caches are off before jumping */
    disable_mmu_el3();

    /* Clear the security state for BL2 (S-EL1) */
    write_scr_el3(SCR_RES1_BITS | SCR_NS_BIT);

    /* Set the entry point and jump */
    bl1_arch_next_el_setup();
    __asm__ volatile(
        "mov x0, %0\n"
        "mov x1, %1\n"
        "br %2\n"
        :
        : "r" (bl2_ep->args.arg0),
          "r" (bl2_ep->args.arg1),
          "r" (bl2_ep->pc)
        : "x0", "x1"
    );
}
```

Key detail: BL1 disables the MMU and clears the NS bit in SCR_EL3, ensuring BL2 starts in the secure world. The `br` instruction jumps directly to BL2’s entry point.

## Common Pitfalls & Gotchas

1. **BL2 memory corruption from BL1**: BL1 typically loads BL2 into DRAM, but if BL1’s DRAM initialization is incomplete (e.g., wrong timing parameters), BL2 will silently crash. Always verify DRAM calibration with a memory test in BL1 before loading BL2. On FVP, use `plat_fvp_dram_init()` debug prints.

2. **FIP image size exceeds BL2’s load buffer**: BL2 has a fixed-size buffer (defined by `PLAT_PARTITION_MAX_SIZE`). If the FIP contains a large BL32 or BL33, BL2 will fail to parse it. The symptom is a `ERROR: Failed to load image` with no further details. Use `fiptool` to inspect the FIP: `./tools/fiptool/fiptool info fip.bin`.

3. **BL31 entry point mismatch**: BL2 passes BL31’s entry point via the `bl31_params` structure. If BL31 is built with a different base address (e.g., `ARM_BL31_BASE` mismatch), the jump will land in uninitialized memory. Always verify `ARM_BL31_BASE` in `plat/fvp/include/platform_def.h` matches the FIP load address.

## Try It Yourself

1. **Trace the boot flow with debug logs**: Build TF-A with `LOG_LEVEL=50` and run on FVP. Capture the console output and identify the exact log lines where BL1 hands off to BL2, and BL2 loads BL31. Look for `INFO: BL1: Loading BL2` and `INFO: BL2: Loading BL31`.

2. **Modify BL2’s memory map**: Increase `BL2_LIMIT` in `plat/fvp/include/platform_def.h` by 0x10000 (64 KB) and rebuild. Use `MEM_MAP_GEN=1` to verify the new layout. Then add a large static buffer in `bl2_main.c` and confirm it fits.

3. **Inject a deliberate handoff error**: In `bl1_run_bl2()`, change the `SCR_NS_BIT` to 0 (forcing BL2 into non-secure state). Rebuild and run. Observe the crash in BL2 when it tries to access secure registers. This demonstrates why the handoff contract is critical.

## Next Up

Tomorrow, we dive into OP-TEE: Trusted Execution Environment Architecture. We’ll explore how BL32 (OP-TEE) initializes, sets up secure memory, and communicates with BL31 via SMCs. You’ll build a custom trusted application and invoke it from Linux—the first step toward real-world TEE usage.
