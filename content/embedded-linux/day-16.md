---
title: "Day 16: Linux Memory Management: Virtual Memory & MMU"
date: 2026-06-28
tags: ["til", "embedded-linux", "memory", "mmu"]
---

## What I Explored Today

Today I dug into the Linux memory management subsystem, specifically how virtual memory and the Memory Management Unit (MMU) work together to give every process its own sandboxed address space. On embedded systems with constrained RAM, understanding this isn't academic—it's the difference between a stable system and one that mysteriously OOM-kills your critical daemon. I traced through `/proc/self/maps`, inspected page table entries with a kernel module, and confirmed that the MMU is doing heavy lifting even on a humble ARM Cortex-A7.

## The Core Concept

Why does Linux bother with virtual memory at all? Because physical memory is a shared, fragmented, and dangerous resource. Without the MMU, every process would see the same physical addresses, a stray pointer in one application could corrupt another's data, and fragmentation would make allocating a large contiguous buffer impossible after the system runs for a few hours.

The MMU translates every memory access from a **virtual address** (what your program sees) to a **physical address** (what the RAM actually has). It does this through page tables—hierarchical data structures that map 4 KiB pages (or 64 KiB, 2 MiB, etc., depending on architecture and configuration). Each process gets its own page table set, so process A's virtual address `0x10000` can map to physical page frame `0xABC000`, while process B's `0x10000` maps to `0xDEF000`. They never collide.

Critically, the MMU also enforces permissions: read, write, execute. On ARMv7-A with LPAE or ARMv8-A, the MMU provides two-stage translation for virtualization and can mark pages as non-executable (NX)—a cornerstone of modern exploit mitigation. In embedded Linux, we often disable the MMU on tiny MCUs (no-MMU or `CONFIG_MMU=n`), but on any application-class processor (Cortex-A, RISC-V with MMU), it's mandatory.

The kernel manages this with the **page allocator** (buddy system for physical pages) and the **virtual memory area (VMA)** abstraction. Every `mmap`, `brk`, or `malloc` call eventually creates or modifies a VMA, which describes a contiguous virtual address range with its backing physical pages and permissions.

## Key Commands / Configuration / Code

**1. Inspect a process's virtual memory layout**

```bash
# Show all VMAs for the current shell
cat /proc/self/maps

# Example output (annotated):
# 00400000-0040c000 r-xp 00000000 08:01 12345     /bin/bash   # text segment
# 0060b000-0060c000 rw-p 0000b000 08:01 12345     /bin/bash   # data segment
# 7f8a400000-7f8a421000 rw-p 00000000 00:00 0     [heap]      # heap
# 7ffc800000-7ffc821000 rw-p 00000000 00:00 0     [stack]     # stack
# 7ffc822000-7ffc824000 r-xp 00000000 00:00 0     [vdso]      # kernel VDSO
```

**2. Dump page table statistics**

```bash
# Show memory usage per process, including page table memory
cat /proc/self/status | grep -E "VmPTE|VmRSS|VmSize"

# System-wide page table memory consumption
grep PageTables /proc/meminfo
```

**3. Kernel code: walking page tables (simplified)**

```c
// From arch/arm/mm/fault.c (simplified for illustration)
// This is what happens inside do_page_fault()

static inline pte_t *get_pte(struct mm_struct *mm, unsigned long addr)
{
    pgd_t *pgd;      // Page Global Directory entry
    p4d_t *p4d;      // Page 4th-level Directory (if CONFIG_PGTABLE_LEVELS > 4)
    pud_t *pud;      // Page Upper Directory
    pmd_t *pmd;      // Page Middle Directory
    pte_t *pte;      // Page Table Entry

    pgd = pgd_offset(mm, addr);
    if (pgd_none(*pgd) || pgd_bad(*pgd))
        return NULL;

    p4d = p4d_offset(pgd, addr);
    if (p4d_none(*p4d) || p4d_bad(*p4d))
        return NULL;

    pud = pud_offset(p4d, addr);
    if (pud_none(*pud) || pud_bad(*pud))
        return NULL;

    pmd = pmd_offset(pud, addr);
    if (pmd_none(*pmd) || pmd_bad(*pmd))
        return NULL;

    pte = pte_offset_map(pmd, addr);
    if (!pte || pte_none(*pte))
        return NULL;

    return pte;  // caller must pte_unmap()
}
```

**4. Check MMU features at runtime**

```bash
# On ARM: read the MMU control register via /dev/mem or CPU registers
# Simpler: check kernel config
zcat /proc/config.gz | grep CONFIG_MMU

# On ARM, check if LPAE (Large Physical Address Extension) is enabled
cat /proc/cpuinfo | grep "Features" | grep lpae
```

## Common Pitfalls & Gotchas

**1. Forgetting that `mmap` with `MAP_ANONYMOUS` doesn't commit physical pages immediately.** The kernel uses demand paging—the page table entry is marked as "not present" until you actually read or write the address. This means you can `mmap` 1 GiB on a system with 512 MiB RAM and it succeeds, but the first access triggers a page fault and an OOM kill. Always check `VmRSS` vs `VmSize` in `/proc/pid/status`.

**2. Confusing virtual address space with physical address space on no-MMU systems.** If you're building a kernel with `CONFIG_MMU=n` (common on Cortex-M or RISC-V without MMU), every process shares the same flat address space. A `malloc` failure there means physical fragmentation, not virtual exhaustion. Debugging tools like `strace` will show `ENOMEM` on `brk` calls that would work fine on an MMU-enabled system.

**3. Page table memory is not free.** On a 32-bit ARM system with 4 KiB pages, each process's page table consumes about 4 KiB per 1 MiB of mapped virtual memory. A process mapping 256 MiB of anonymous pages burns ~1 MiB of kernel memory just for page tables. On memory-constrained embedded systems, this can be a hidden tax. Monitor with `grep PageTables /proc/meminfo` and consider using huge pages (`CONFIG_TRANSPARENT_HUGEPAGE`) to reduce page table overhead.

## Try It Yourself

1. **Map your own process:** Run `cat /proc/$$/maps` in a shell. Identify the heap, stack, and at least one shared library. Note the permissions (`r-xp` vs `rw-p`). Then run `strace -e trace=mmap,munmap cat /dev/null` and watch the kernel create and destroy VMAs in real time.

2. **Measure page table overhead:** Write a small C program that `mmap`s 100 MiB of anonymous memory, then sleeps. While it sleeps, run `cat /proc/<pid>/status | grep VmPTE` to see the page table memory cost. Compare with a version that uses `MAP_HUGETLB` (if your kernel supports huge pages).

3. **Trigger a page fault and observe:** Use `perf` to count page faults: `perf stat -e page-faults,minor-faults,major-faults find /usr -name "*.so"`. Then explain why the first run has many major faults (cold cache) and subsequent runs have only minor faults (pages already in page cache).

## Next Up

Tomorrow: **Memory Allocation: kmalloc, vmalloc, DMA Memory** — I'll break down when to use the slab allocator vs. the vmalloc region, why DMA memory must be physically contiguous, and how to avoid the common mistake of using `kmalloc` for large buffers on systems with high memory fragmentation.
