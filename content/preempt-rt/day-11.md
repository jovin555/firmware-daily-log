---
title: "Day 11: Memory: Huge Pages, mlockall & Page Faults in RT"
date: 2026-06-23
tags: ["til", "preempt-rt", "hugepages", "page-faults", "mlockall"]
---

## What I Explored Today

Memory management is the silent killer of real-time determinism. Today I dug into how page faults, transparent huge pages, and memory locking interact with PREEMPT_RT. The short version: a single major page fault can cost 10+ milliseconds — an eternity in a 1 kHz control loop. I tested `mlockall()`, configured explicit huge pages, and measured the latency impact of lazy allocation. The results confirm that default Linux memory behavior is fundamentally incompatible with hard real-time constraints.

## The Core Concept

Real-time guarantees are about *predictability*, not just speed. The Linux virtual memory subsystem is optimized for throughput and overcommit — it defers physical page allocation until the last possible moment (demand paging). This is catastrophic for RT.

When your real-time thread touches a memory address for the first time, the CPU raises a page fault. The kernel must:
1. Walk the page tables to confirm the fault is valid
2. Find or allocate a physical page frame
3. Zero-fill the page (for anonymous mappings)
4. Update the TLB and page table entries
5. Return to userspace

A minor page fault (page already in memory but not mapped) takes ~1-5 µs. A major page fault (requires disk I/O for swap) can take **milliseconds**. Even worse: Transparent Huge Pages (THP) can cause *compaction* — the kernel defragments memory to create a 2 MB huge page — which introduces unpredictable multi-millisecond stalls.

The fix is threefold:
- **Lock all memory** with `mlockall()` to prevent swapping and page-out
- **Prefault and touch** all pages at initialization time, before the RT thread starts
- **Use explicit huge pages** (hugetlbfs) to reduce TLB pressure and eliminate THP compaction

## Key Commands / Configuration / Code

### 1. Lock memory and prefault in C

```c
#define _GNU_SOURCE
#include <sys/mman.h>
#include <unistd.h>
#include <stdlib.h>

#define BUF_SIZE (64 * 1024 * 1024)  // 64 MB buffer

int main() {
    // Lock all current and future pages into RAM
    if (mlockall(MCL_CURRENT | MCL_FUTURE) == -1) {
        perror("mlockall failed");
        exit(1);
    }

    // Allocate and immediately touch every page
    char *buf = malloc(BUF_SIZE);
    if (!buf) exit(1);

    // Prefault: write one byte per page (4 KB stride)
    size_t page_size = sysconf(_SC_PAGESIZE);
    for (size_t i = 0; i < BUF_SIZE; i += page_size) {
        buf[i] = 0;  // This triggers the page fault NOW
    }

    // Now buf is fully resident and locked — no faults during RT loop
    // ... real-time work here ...

    munlockall();
    free(buf);
    return 0;
}
```

### 2. Configure explicit huge pages (hugetlbfs)

```bash
# Reserve 16 huge pages (each 2 MB on x86_64) at boot
# Add to kernel cmdline: default_hugepagesz=2M hugepages=16

# Or at runtime (requires sufficient contiguous memory)
echo 16 > /proc/sys/vm/nr_hugepages

# Verify reservation
grep HugePages_Total /proc/meminfo
# Output: HugePages_Total:      16

# Mount hugetlbfs and use in code
mkdir -p /mnt/huge
mount -t hugetlbfs hugetlbfs /mnt/huge -o pagesize=2M
```

### 3. Disable transparent huge pages (critical for RT)

```bash
# Check current state
cat /sys/kernel/mm/transparent_hugepage/enabled
# Typical output: [always] madvise never

# Disable entirely (recommended for RT)
echo never > /sys/kernel/mm/transparent_hugepage/enabled

# Also disable defrag (compaction)
echo never > /sys/kernel/mm/transparent_hugepage/defrag
```

### 4. Verify no page faults during RT execution

```bash
# Run your RT process with PID monitoring
# Check major page faults
grep maj_flt /proc/$PID/status
# Should be 0 after initialization phase

# Monitor real-time page faults with perf
perf stat -e page-faults,major-faults,minor-faults -p $PID sleep 1
```

## Common Pitfalls & Gotchas

**1. `mlockall(MCL_FUTURE)` doesn't prefault — it only prevents swapping.** You must explicitly touch every page after allocation. I've seen teams add `mlockall` and wonder why they still get page faults on first access. The lock prevents the kernel from *evicting* pages, but it doesn't force them to be *allocated*.

**2. Huge page reservation can fail silently.** If you request 16 huge pages but only 12 contiguous 2 MB blocks are available, `nr_hugepages` will show 12. Always check `/proc/meminfo` after reservation. Also, huge pages are not swappable — once allocated, they stay. This can exhaust memory if you're not careful.

**3. THP compaction is a hidden latency bomb.** Even with `madvise` mode, the kernel may trigger compaction when a process uses `madvise(MADV_HUGEPAGE)`. This can stall your RT thread for 10-100 ms. Always set `transparent_hugepage/enabled` to `never` on RT systems. The TLB miss cost of 4 KB pages is far less damaging than a compaction stall.

**4. `malloc` may not return huge-page-aligned memory.** If you use hugetlbfs, you must use `mmap()` with `MAP_HUGETLB` or allocate from a hugetlbfs file descriptor. `malloc` and `calloc` won't automatically use huge pages.

## Try It Yourself

**Task 1: Measure page fault latency**
Write a small C program that allocates 256 MB, locks it with `mlockall(MCL_CURRENT | MCL_FUTURE)`, and then measures the time to touch each page (use `clock_gettime` with `CLOCK_MONOTONIC`). Run it twice — once with prefaulting, once without. Compare the max latency.

**Task 2: Configure and test huge pages**
Reserve 64 huge pages (2 MB each) on your test system. Write a program that uses `mmap` with `MAP_HUGETLB` to allocate a 128 MB buffer. Verify with `cat /proc/meminfo | grep HugePages` that the count decreases. Measure the TLB miss rate with `perf stat -e dTLB-load-misses` versus a normal 4 KB allocation.

**Task 3: Disable THP and measure max latency**
Run a cyclic test (like `cyclictest`) with THP enabled (`always`), then with THP disabled (`never`). Use `tuna` to pin the test thread to a dedicated CPU. Compare the maximum observed latency over a 10-minute run. The THP-enabled run should show occasional spikes >100 µs.

## Next Up

Tomorrow: **Priority Inversion & Priority Inheritance Mutexes** — the classic real-time bug that can turn a high-priority task into a blocked victim. We'll trace a real priority inversion scenario and implement the fix using `PTHREAD_PRIO_INHERIT`.
