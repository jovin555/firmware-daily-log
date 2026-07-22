---
title: "Day 22: Side-Channel Resistance: Constant-Time Crypto Implementations"
date: 2026-07-22
tags: ["til", "embedded-crypto", "side-channel", "constant-time"]
---

## What I Explored Today

Today I dug into the practical reality of side-channel attacks on embedded cryptographic implementations, specifically focusing on timing attacks and their mitigation through constant-time code. I've known for years that AES-GCM on a Cortex-M4 can leak the key through cache timing, but until I instrumented an actual implementation with a logic analyzer, I didn't appreciate how *trivial* these attacks are to execute. The core lesson: cryptographic algorithms are mathematically secure, but their *implementations* on real hardware leak secrets through execution time, power consumption, and electromagnetic emissions. Constant-time programming is the first line of defense, and it's harder than it looks.

## The Core Concept

Timing attacks exploit the fact that most CPUs execute different code paths in different amounts of time. A classic example: comparing a MAC (Message Authentication Code) byte-by-byte with `memcmp`. The moment a byte mismatches, `memcmp` returns early. An attacker measures response time, iteratively guesses each byte, and recovers the entire secret in at most 256×N attempts instead of 256^N.

The fix is *constant-time* execution: the same number of CPU cycles regardless of input values or secret data. This means:
- No conditional branches based on secret data
- No variable-time instructions (division, some multiplication)
- No table lookups indexed by secrets (cache timing leaks)
- No early exits from loops

On embedded targets, this often means writing in assembly or using compiler intrinsics to guarantee timing behavior. The compiler is not your friend here—it will "optimize" your constant-time code into variable-time code unless you explicitly prevent it.

## Key Commands / Configuration / Code

### Constant-Time Memory Compare (for Cortex-M4)

```c
// Constant-time memory comparison
// Returns 0 if equal, non-zero otherwise
// No early exit — every byte always compared
int ct_memcmp(const void *a, const void *b, size_t len) {
    const uint8_t *pa = (const uint8_t *)a;
    const uint8_t *pb = (const uint8_t *)b;
    uint8_t result = 0;
    
    for (size_t i = 0; i < len; i++) {
        result |= pa[i] ^ pb[i];  // XOR accumulates mismatch
    }
    
    // Constant-time: always returns result, never branches on secret
    return (int)result;
}
```

### Constant-Time Conditional Select (no branches)

```c
// Constant-time select: returns 'a' if condition is 0, 'b' otherwise
// Condition MUST be 0 or 1 (not arbitrary boolean)
uint32_t ct_select(uint32_t a, uint32_t b, uint32_t condition) {
    // condition must be 0 or 1
    uint32_t mask = 0 - condition;  // 0 -> 0x00000000, 1 -> 0xFFFFFFFF
    return (a & ~mask) | (b & mask);
}
```

### Compiler Barrier to Prevent Optimizations

```c
// Prevent compiler from optimizing away constant-time operations
// Place after secret-dependent operations
static inline void ct_compiler_barrier(void) {
    __asm__ volatile("" ::: "memory");
}
```

### Checking Timing with a Logic Analyzer

```bash
# On host, using Saleae Logic or similar
# Probe GPIO pin toggled before/after crypto operation
# Use pulseview for open-source alternative:
pulseview -i timing_capture.sr -I srzip

# Or use a simple oscilloscope with trigger on GPIO rising edge
# Measure time between GPIO toggle with 1ns resolution
```

### Build Configuration for Constant-Time (GCC)

```makefile
# Disable optimizations that break constant-time
CFLAGS += -O2 -fno-tree-vectorize -fno-schedule-insns -fno-schedule-insns2
# Prevent loop unrolling that might expose timing
CFLAGS += -fno-unroll-loops
# Ensure volatile accesses are not reordered
CFLAGS += -fno-strict-aliasing
```

## Common Pitfalls & Gotchas

**1. Compiler "Optimizes" Your Constant-Time Code Away**
The most insidious problem. You write a careful constant-time loop, and GCC decides that since the result is always the same (you're comparing two equal buffers in a test), it can just skip the loop entirely. Always test with *different* inputs, and use `volatile` or compiler barriers to force the compiler to emit the actual operations. I've seen production code where the constant-time compare was reduced to `return 0;` by -O3.

**2. Cache Timing Leaks from Table Lookups**
Even if your code has no branches, a table lookup indexed by a secret byte will leak which entry was accessed through cache timing. AES T-table implementations are famously vulnerable. On Cortex-M7 with L1 cache, a single table access can leak 4-6 bits of key material. Solution: use bit-slicing or hardware AES accelerators (like CRYP on STM32) instead of software table lookups.

**3. Variable-Time Instructions on Cortex-M**
Division (`SDIV`/`UDIV`) takes 2-12 cycles depending on the operands. Multiplication (`MUL`) is constant on M4/M7 but not on M0/M0+. The `CLZ` (count leading zeros) instruction is constant-time on M3/M4 but not on M0. Always check the architecture reference manual for instruction timing—don't assume.

## Try It Yourself

1. **Instrument your existing crypto**: Add GPIO toggles before and after your MAC verification routine. Capture timing with a logic analyzer while sending valid and invalid MACs. Can you see the timing difference? If yes, you have a side-channel vulnerability.

2. **Rewrite `memcmp` as constant-time**: Take your bootloader's firmware signature verification and replace `memcmp` with `ct_memcmp`. Verify it still works correctly, then measure execution time with different inputs—it should be constant within ±1 cycle.

3. **Test compiler optimization**: Write a constant-time conditional select function. Compile with `-O3` and inspect the assembly (`objdump -d`). Does it still have no branches? Try adding `__attribute__((noinline))` and a compiler barrier. Compare the assembly output.

## Next Up

**Day 23: Post-Quantum Cryptography: What Embedded Engineers Need to Know Now** — NIST has standardized CRYSTALS-Kyber (ML-KEM) and CRYSTALS-Dilithium (ML-DSA). But can your Cortex-M0 run them in under a second? We'll look at real benchmarks, memory footprints, and what you need to start planning for the quantum transition today.
