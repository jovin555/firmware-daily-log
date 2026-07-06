---
title: "Day 06: A/B Slot Swap Algorithms: Bank Swap vs Scratch-Area Swap"
date: 2026-07-06
tags: ["til", "secure-ota", "swap-algorithm"]
---

## What I Explored Today

Today I dug into the two dominant strategies for swapping firmware slots after an A/B update completes: **bank swap** (also called direct swap or pointer swap) and **scratch-area swap** (also called copy-swap or buffered swap). While both achieve the same end goal—making the newly updated firmware the active boot target—they differ fundamentally in how they handle atomicity, wear-leveling, and recovery from power loss mid-swap. I implemented both on a STM32H7 dual-bank flash part and a simulated QSPI NOR flash to understand the tradeoffs in real hardware.

## The Core Concept

The entire point of an A/B update is that you can boot into either slot (A or B) independently. After a successful update to the inactive slot, you need to make that slot the *primary* boot target. The swap algorithm is the mechanism that flips this pointer.

**Bank swap** relies on the MCU’s flash controller supporting hardware bank remapping. On STM32, you set the `BANK_SWAP` bit in the option bytes, and the memory map physically swaps: the address range `0x0800_0000` now points to what was previously the second bank. This is nearly instantaneous (one register write) and inherently atomic—either the swap happened or it didn’t. No data movement occurs.

**Scratch-area swap** is used when you don’t have hardware bank remapping, or when your slots are on external QSPI NOR flash. Here, you copy the newly updated slot into a scratch buffer (usually internal SRAM or a reserved flash region), erase the active slot, then copy the new image back. This is slower, consumes RAM, and is vulnerable to power loss during the copy. To mitigate that, you typically use a two-phase commit with a persistent "swap-in-progress" flag in a protected flash sector.

The choice between them isn’t just about hardware capability—it’s about your system’s tolerance for risk. Bank swap is fast and safe but inflexible. Scratch-area swap is flexible (you can swap any two regions, not just hardware banks) but requires careful power-loss recovery design.

## Key Commands / Configuration / Code

### Bank Swap on STM32H7 (Option Bytes)

```c
// Enable write access to option bytes
HAL_FLASH_OB_Unlock();

// Read current option bytes
FLASH_OBProgramInitTypeDef ob;
HAL_FLASHEx_OBGetConfig(&ob);

// Toggle BANK_SWAP bit (bit 23 in OPTCR)
if (ob.USERConfig & OB_BANK_SWAP_MODE) {
    ob.USERConfig &= ~OB_BANK_SWAP_MODE;  // Swap back to default
} else {
    ob.USERConfig |= OB_BANK_SWAP_MODE;   // Swap banks
}

// Write new option bytes and force a system reset
HAL_FLASHEx_OBProgram(&ob);
HAL_FLASH_OB_Launch();  // This triggers a reset—swap takes effect immediately
```

### Scratch-Area Swap with Power-Loss Safety (Pseudocode)

```c
#define SWAP_FLAG_ADDR  0x081F0000  // Last sector of internal flash, reserved
#define SWAP_IN_PROGRESS 0x5A5A5A5A
#define SWAP_COMPLETE    0xA5A5A5A5

bool scratch_area_swap(uint32_t src_addr, uint32_t dst_addr, uint32_t size) {
    uint8_t *scratch = malloc(size);  // Must fit in RAM—check your heap
    
    // Phase 1: Write "swap in progress" flag
    write_uint32(SWAP_FLAG_ADDR, SWAP_IN_PROGRESS);
    __DMB();  // Data memory barrier—ensure flag is flushed
    
    // Phase 2: Copy new image to scratch
    memcpy(scratch, (void*)src_addr, size);
    
    // Phase 3: Erase destination slot
    flash_erase(dst_addr, size);
    
    // Phase 4: Write new image to destination
    flash_write(dst_addr, scratch, size);
    
    // Phase 5: Mark swap complete
    write_uint32(SWAP_FLAG_ADDR, SWAP_COMPLETE);
    
    free(scratch);
    return true;
}

// On boot, check SWAP_FLAG_ADDR:
void recovery_check(void) {
    uint32_t flag = read_uint32(SWAP_FLAG_ADDR);
    if (flag == SWAP_IN_PROGRESS) {
        // Power loss during swap—re-copy from source slot
        scratch_area_swap(SOURCE_SLOT, ACTIVE_SLOT, FIRMWARE_SIZE);
    }
}
```

### Bootloader Slot Selection (Both Methods)

```c
// Bank swap: bootloader just reads the hardware remap status
bool is_bank_swapped(void) {
    FLASH_OBProgramInitTypeDef ob;
    HAL_FLASHEx_OBGetConfig(&ob);
    return (ob.USERConfig & OB_BANK_SWAP_MODE) != 0;
}

// Scratch-area swap: bootloader reads a "slot active" flag in a known flash location
bool is_slot_b_active(void) {
    return read_uint32(SLOT_ACTIVE_FLAG_ADDR) == SLOT_B_MAGIC;
}
```

## Common Pitfalls & Gotchas

**1. Bank swap on dual-bank parts requires symmetric banks.** If your two flash banks aren’t identical in size (e.g., Bank 1 = 1 MB, Bank 2 = 512 KB), the hardware swap will map the smaller bank into the boot address space, truncating your larger firmware. Always verify `FLASH_BANK1_SIZE == FLASH_BANK2_SIZE` at compile time with a static assert.

**2. Scratch-area swap can silently corrupt if the scratch buffer overlaps the destination.** If you allocate your scratch buffer from the same flash region you’re erasing, you’ll read garbage after the erase. Always ensure the scratch buffer lives in a completely separate memory domain (internal SRAM or a dedicated reserved flash sector).

**3. Power-loss recovery in scratch-area swap is only safe if the flag write is atomic.** On NOR flash, a single word write is atomic, but if you’re using a filesystem or wear-leveling layer, the flag update may involve multiple writes. Use a raw flash write at a known, fixed address, and verify the flag value after writing.

## Try It Yourself

1. **Implement a bank swap toggle on an STM32H7 Nucleo.** Write a small program that reads the current `BANK_SWAP` option byte, toggles it, and calls `HAL_FLASH_OB_Launch()`. Use a debugger to verify the memory map changes at `0x0800_0000` after reset.

2. **Build a scratch-area swap with a simulated power loss.** Use an external button to trigger a swap, then pull the plug mid-copy. Add the recovery check in your bootloader and verify it re-copies the correct slot on next boot.

3. **Measure the swap time for both methods.** On your target hardware, toggle a GPIO before and after the swap operation, and capture the pulse width on an oscilloscope. Compare bank swap (~10 µs) vs scratch-area swap (seconds for a 1 MB image over QSPI).

## Next Up

Tomorrow: **Delta/Differential Updates: bsdiff, Courgette & Binary Patching** — how to ship only the changed bytes instead of the entire firmware, and why Courgette’s approach differs from bsdiff for executable code.
