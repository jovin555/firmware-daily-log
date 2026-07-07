---
title: "Day 07: Delta/Differential Updates: bsdiff, Courgette & Binary Patching"
date: 2026-07-07
tags: ["til", "secure-ota", "delta-update", "bsdiff"]
---

## What I Explored Today

Today I dove into delta (differential) update algorithms—specifically bsdiff and Courgette—to understand how they generate small binary patches from two firmware versions. I built a test pipeline that produces a patch file from v1.0 to v1.1 of a firmware image, then applied it on a simulated constrained device. The results were striking: a 512 KB firmware update shrank to a 23 KB patch when only a few driver modules changed.

## The Core Concept

Full-image OTA updates are simple but wasteful. If you change one line of code in a 1 MB firmware, the device still downloads the entire 1 MB. Delta updates solve this by sending only the *difference* between the old and new binary.

The key insight: firmware binaries are not random. They contain repeated instruction sequences, function prologues/epilogues, and constant pools. A good delta algorithm exploits this structure. bsdiff uses suffix sorting (like building a suffix array) to find long common substrings, then encodes only the changed bytes plus a copy/literal stream. Courgette goes further: it disassembles the binary, matches functions at the instruction level, and emits a patch that can be applied even when addresses shift due to linker changes.

For embedded systems, the trade-off is clear: patch generation is computationally expensive (minutes on a build server), but patch application must be cheap (seconds on a Cortex-M4). Both bsdiff and Courgette prioritize fast apply at the cost of slow generate.

## Key Commands / Configuration / Code

### 1. Generating a bsdiff patch

```bash
# Install bsdiff on build server
sudo apt-get install bsdiff

# Generate patch from firmware_v1.bin to firmware_v2.bin
# Output: firmware_v1_to_v2.patch
bsdiff firmware_v1.bin firmware_v2.bin firmware_v1_to_v2.patch

# Check patch size
ls -lh firmware_v1_to_v2.patch
# Example output: -rw-r--r-- 1 user user 23K Jul  7 14:22 firmware_v1_to_v2.patch
```

### 2. Applying the patch on the device (C pseudocode)

```c
#include <bsdiff/bsdiff.h>  // Embedded port of bsdiff

// Device-side patch application
// Assumes old firmware in external flash, patch in download buffer
int apply_delta_update(
    const uint8_t* old_fw,    // Pointer to current firmware in flash
    size_t        old_size,   // e.g., 524288 (512 KB)
    const uint8_t* patch,     // Patch data received via OTA
    size_t        patch_size, // e.g., 23552 (23 KB)
    uint8_t*       new_fw,    // Output buffer (must be old_size or larger)
    size_t*        new_size   // Output size
) {
    // bspatch() from the embedded bsdiff port
    // Returns 0 on success, -1 on error
    int ret = bspatch(old_fw, old_size, new_fw, new_size, patch, patch_size);
    if (ret != 0) {
        // Log error, trigger fallback to full update
        return -1;
    }
    // Verify CRC/SHA of new_fw before committing
    return 0;
}
```

### 3. Courgette (Chromium's approach) — conceptual flow

```bash
# Courgette is part of Chromium's build system
# Generate Courgette patch (requires disassembly)
courgette -gen firmware_v1.bin firmware_v2.bin firmware_v1_to_v2.courgette

# Apply Courgette patch
courgette -apply firmware_v1.bin firmware_v1_to_v2.courgette firmware_v2_reconstructed.bin

# Compare sizes
ls -lh firmware_v1_to_v2.courgette   # Typically 30-50% smaller than bsdiff
ls -lh firmware_v1_to_v2.patch       # bsdiff version
```

### 4. Verifying patch integrity

```bash
# Always verify the reconstructed binary matches the original
sha256sum firmware_v2.bin firmware_v2_reconstructed.bin
# Both should produce identical hashes

# If using custom patch format, embed a CRC in the patch header
# Example: first 4 bytes = CRC32 of new firmware after apply
```

## Common Pitfalls & Gotchas

1. **Memory constraints kill naive bsdiff apply.** The standard bsdiff apply algorithm allocates a buffer the size of the *new* firmware plus the *old* firmware. On a 1 MB device, that's 2 MB RAM. Always use the streaming variant (`bspatch_stream`) that processes in chunks, or use a memory-mapped external flash.

2. **Linker changes destroy delta efficiency.** If you add a single function to the middle of a source file, the linker shifts all subsequent addresses. bsdiff sees this as a massive change—the patch balloons. Courgette handles this via instruction-level matching, but it requires the toolchain to emit relocatable code. For bare-metal firmware, consider function-level section placement to minimize address shifts.

3. **Patch generation is not idempotent.** Running bsdiff twice on the same pair of binaries may produce slightly different patches due to suffix array implementation details. Always verify the reconstructed binary with a cryptographic hash, not by comparing patch files.

## Try It Yourself

1. **Generate a delta for a real firmware change.** Take two compiled firmware binaries (e.g., before and after adding a new driver). Run `bsdiff` and compare the patch size to the full image. Calculate the savings percentage.

2. **Stress-test patch application on constrained hardware.** Port the `bspatch` streaming variant to your target MCU. Measure RAM usage during apply. If it exceeds available SRAM, implement a chunked apply that reads old firmware from external flash in 4 KB blocks.

3. **Compare bsdiff vs. Courgette on your firmware.** If you can build Courgette (it's complex), generate both patch types. For many embedded binaries, Courgette's patches are 30-50% smaller, but the generation time is 10x longer. Decide which trade-off fits your OTA pipeline.

## Next Up

Tomorrow: **Compressing Firmware Images: LZ4, zlib & Constrained Flash** — we'll explore how to shrink firmware images before delta generation, and why LZ4's decompression speed matters more than compression ratio when your CPU runs at 48 MHz.
