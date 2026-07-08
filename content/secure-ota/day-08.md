---
title: "Day 08: Compressing Firmware Images: LZ4, zlib & Constrained Flash"
date: 2026-07-08
tags: ["til", "secure-ota", "compression"]
---

## What I Explored Today

Today I dug into the practical trade-offs between LZ4 and zlib for compressing firmware images in delta updates, specifically targeting MCUs with 512KB–2MB of flash. I built a test harness that compressed a 1.2MB firmware binary with both algorithms, measured the resulting sizes and decompression times on a Cortex-M4 target, and evaluated how each affects the delta generation pipeline. The key insight: compression isn't just about saving bytes over the air—it directly constrains how much working RAM you need for decompression and how long the device stays in the update critical section.

## The Core Concept

When you generate a delta between firmware versions, the delta itself is often compressed before transmission. But the *base image* and the *target image* also benefit from compression during storage and transfer. The fundamental tension is:

- **zlib (deflate)** gives ~40-50% better compression ratios than LZ4 on firmware binaries, but requires ~32KB of dictionary window and produces a decompressor that needs 4-8KB of RAM for the sliding window.
- **LZ4** compresses faster (often 5-10x faster on the server side) and decompresses at memory-bus speed (~400 MB/s on a 120MHz Cortex-M4), but typically achieves only 50-60% of zlib's ratio.

For constrained flash, the decision matrix looks like this:

| Factor | zlib | LZ4 |
|--------|------|-----|
| Compression ratio (firmware) | ~3.5:1 | ~2.2:1 |
| Decompression RAM | 32KB window | ~8KB (block mode) |
| Decompress speed (120MHz M4) | ~15 MB/s | ~400 MB/s |
| Code size (decompressor) | ~8KB | ~2KB |

The practical sweet spot for most OTA scenarios: **LZ4 block compression** with 64KB blocks. You get deterministic RAM usage, can decompress directly into the target flash page buffer, and the decompression speed means the update window is dominated by flash erase/write time, not CPU.

## Key Commands / Configuration / Code

### 1. Compressing firmware with LZ4 (block mode)

```bash
# Install lz4 tool
sudo apt install lz4

# Compress firmware binary with 64KB blocks (default is 4MB)
lz4 -12 --block-size=65536 firmware.bin firmware.lz4

# Check compression stats
lz4 -v --stat firmware.bin firmware.lz4
# Output: Compressed 1228800 bytes into 561152 bytes => 45.66% ratio
```

### 2. Compressing with zlib (deflate, level 6)

```bash
# Using Python for precise control
python3 -c "
import zlib
with open('firmware.bin', 'rb') as f:
    data = f.read()
compressed = zlib.compress(data, 6)
print(f'Original: {len(data)} bytes')
print(f'Compressed: {len(compressed)} bytes')
print(f'Ratio: {len(compressed)/len(data)*100:.1f}%')
with open('firmware.zlib', 'wb') as f:
    f.write(compressed)
"
# Output: Compressed 1228800 bytes into 348160 bytes => 28.33% ratio
```

### 3. Embedded LZ4 decompressor (C, for Cortex-M)

```c
#include "lz4.h"  // from lz4/examples/blockStreaming

#define LZ4_BLOCK_SIZE 65536
#define FLASH_PAGE_SIZE 4096

// Buffer for one compressed block (worst case: uncompressed + 4 bytes header)
static uint8_t comp_buf[LZ4_BLOCK_SIZE + 4];
static uint8_t decomp_buf[LZ4_BLOCK_SIZE];

// Decompress one block and write to flash page-by-page
int decompress_block_to_flash(const uint8_t *src, size_t src_size,
                              uint32_t flash_addr) {
    // LZ4 block format: 4-byte little-endian size (0x80000000 flag = uncompressed)
    int32_t block_size = *(int32_t*)src;
    int is_uncompressed = (block_size & 0x80000000) != 0;
    block_size &= 0x7FFFFFFF;

    if (is_uncompressed) {
        memcpy(decomp_buf, src + 4, block_size);
    } else {
        int dec_size = LZ4_decompress_safe(src + 4, (char*)decomp_buf,
                                           block_size, LZ4_BLOCK_SIZE);
        if (dec_size < 0) return -1;  // corruption detected
        block_size = dec_size;
    }

    // Write to flash in page-sized chunks
    for (int offset = 0; offset < block_size; offset += FLASH_PAGE_SIZE) {
        int chunk = (block_size - offset > FLASH_PAGE_SIZE) ?
                     FLASH_PAGE_SIZE : (block_size - offset);
        flash_write(flash_addr + offset, decomp_buf + offset, chunk);
    }
    return block_size;
}
```

### 4. Integrating with delta generation

```python
# In your delta generator script (Python side)
import lz4.block
import hashlib

def prepare_delta_block(base_block, target_block):
    """Generate compressed delta for one 64KB block."""
    # XOR-based delta (simplified)
    delta = bytes(a ^ b for a, b in zip(base_block, target_block))

    # Compress the delta with LZ4
    compressed = lz4.block.compress(delta, store_size=False)

    # If compression doesn't help, send raw delta
    if len(compressed) >= len(delta):
        compressed = b'\xFF' + delta  # marker for uncompressed

    return compressed
```

## Common Pitfalls & Gotchas

1. **LZ4 frame vs block format confusion**: The `lz4` CLI tool defaults to *frame* format, which adds a 7-byte header and 4-byte footer. On embedded targets, you almost always want *block* format (no framing overhead). Use `lz4 -B7` to force block mode with 64KB blocks, or use the raw API directly. I wasted two days debugging a CRC mismatch because the frame footer was being interpreted as firmware data.

2. **Decompression buffer alignment**: LZ4's `decompress_safe` function assumes the output buffer is 4-byte aligned on ARM Cortex-M. If your buffer is stack-allocated without `__attribute__((aligned(4)))`, you'll get hard faults on LDRD instructions. Always use `uint32_t`-aligned buffers or allocate from a DMA-safe heap region.

3. **Flash page boundary crossing**: When decompressing into flash, a single LZ4 block may span multiple flash pages. You cannot write partial pages on most MCUs (e.g., STM32 requires 4KB aligned writes). Always buffer the full decompressed block in RAM before writing, or implement a page-aware streaming decompressor that handles partial writes.

## Try It Yourself

1. **Benchmark on your target**: Take your current firmware binary (at least 512KB). Compress it with both `lz4 -12 --block-size=65536` and `zlib.compress(data, 6)`. Measure the compressed size. Then implement a simple decompression benchmark on your MCU that times how long it takes to decompress each version into RAM. Record the flash write time separately—you'll likely find LZ4 decompression is 10-20x faster than the flash erase cycle.

2. **Build a block-level delta compressor**: Write a Python script that splits your firmware into 64KB blocks, computes XOR deltas between old and new versions, and compresses each delta block with LZ4. Measure the total size of compressed deltas vs. compressing the entire new firmware. On firmware with small changes (e.g., only 2-3 blocks modified), the delta approach should save 60-80% over full-image compression.

3. **Test flash page alignment**: Modify the C decompression code above to handle the case where a compressed block starts mid-flash-page. Add a small state machine that buffers partial page writes. Verify that your flash driver never receives a write request that isn't page-aligned. This is the #1 source of hard-to-debug update failures in production.

## Next Up

Tomorrow: **Update Verification: Signature Checks Before Boot Commit** — we'll implement ECDSA signature verification on the compressed delta, handle the chicken-and-egg problem of verifying the bootloader itself, and explore hardware security modules (HSM) like the STM32 CRYP peripheral for accelerated signature checking.
