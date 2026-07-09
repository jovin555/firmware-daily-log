---
title: "Day 09: Buffer Overflows in C: Stack Smashing & Mitigations"
date: 2026-07-09
tags: ["til", "threat-modeling", "buffer-overflow", "stack-smashing"]
---

## What I Explored Today

Today I dug into the mechanics of stack-based buffer overflows in C — specifically how a missing bounds check on a local array can corrupt the return address and hijack control flow. I built a minimal vulnerable program, observed the crash with GDB, then applied three mitigations: stack canaries, ASLR, and manual bounds checking. The goal was to understand *why* these mitigations work at the assembly level, not just how to flip compiler flags.

## The Core Concept

A buffer overflow happens when you write more data into a stack-allocated array than it can hold. The stack grows downward (toward lower addresses), but buffers are filled upward (toward higher addresses). On x86-64, the layout of a stack frame for a function call looks like this (from low to high address):

```
[local variables]  ← buffer[64] lives here
[old RBP]          ← saved base pointer (8 bytes)
[return address]   ← where execution resumes after `ret`
[function args]    ← if any
```

If you write past `buffer[63]`, you overwrite the saved RBP first, then the return address. An attacker who controls the input can place a new return address pointing to shellcode (or a ROP gadget) elsewhere in memory. This is "stack smashing."

The key insight: **the compiler doesn't enforce bounds at runtime by default**. The hardware has no idea where your array ends. It's purely a software contract that we routinely break.

## Key Commands / Configuration / Code

### 1. Vulnerable Program (`vuln.c`)

```c
#include <stdio.h>
#include <string.h>

void vulnerable(void) {
    char buffer[64];                     // stack buffer, 64 bytes
    printf("Enter data: ");
    gets(buffer);                        // NO bounds check — classic
    printf("You entered: %s\n", buffer);
}

int main(void) {
    vulnerable();
    return 0;
}
```

Compile with no protections (for demonstration only):

```bash
gcc -fno-stack-protector -no-pie -z execstack -o vuln vuln.c
# -fno-stack-protector  : disable stack canary
# -no-pie               : disable ASLR for binary base
# -z execstack          : allow execution on stack (shellcode)
```

### 2. Trigger the overflow

```bash
python3 -c "print('A'*72 + 'BBBBBBBB')" | ./vuln
# 64 bytes fill buffer, 8 bytes overwrite saved RBP, 8 bytes overwrite ret addr
# Expect: Segmentation fault (core dumped)
```

### 3. Enable stack canary (GCC default since ~4.8)

```bash
gcc -fstack-protector-strong -o vuln_canary vuln.c
# This adds a random value (canary) between buffer and saved RBP.
# If overflow touches it, __stack_chk_fail aborts the program.
```

### 4. Check canary presence in disassembly

```bash
objdump -d vuln_canary | grep -A 20 "<vulnerable>:"
# Look for:
#   mov    %fs:0x28,%rax    # load canary from thread-local storage
#   mov    %rax,-0x8(%rbp)  # store it on stack
#   ...
#   mov    -0x8(%rbp),%rax
#   sub    %fs:0x28,%rax    # check canary before ret
#   jne    <__stack_chk_fail>
```

### 5. Manual bounds checking (the right way)

```c
#include <stdio.h>
#include <string.h>

void safe(void) {
    char buffer[64];
    printf("Enter data: ");
    if (fgets(buffer, sizeof(buffer), stdin) == NULL) {
        return;                          // fgets limits to 63 chars + null
    }
    buffer[strcspn(buffer, "\n")] = '\0'; // strip trailing newline
    printf("You entered: %s\n", buffer);
}
```

## Common Pitfalls & Gotchas

1. **`gets()` is never safe — but neither is `scanf("%s", ...)`**  
   `gets()` was removed from C11, but `scanf("%s", buf)` is equally dangerous — it doesn't limit input length. Always use `fgets()` or `scanf("%63s", buf)` with explicit field width.

2. **Stack canaries don't protect heap or BSS overflows**  
   Canaries only guard stack frames. If your overflow is in a `malloc`'d buffer or a global array, the canary won't help. You need bounds checking or guard pages.

3. **ASLR can be bypassed with information leaks**  
   Address Space Layout Randomization makes it harder to guess the target address, but if the attacker can leak a pointer (e.g., via format string bug), they can compute the base and bypass ASLR. Stack canaries remain effective even with a leak.

## Try It Yourself

1. **Modify the vulnerable program** to use `strcpy(buffer, argv[1])` instead of `gets()`. Compile with `-fno-stack-protector` and find the exact number of bytes needed to overwrite the return address with `0x4141414141414141`. Use GDB to confirm.

2. **Recompile with `-fstack-protector-strong`** and try the same overflow. Observe the `*** stack smashing detected ***` message. Use `objdump` to locate the canary check in the disassembly.

3. **Write a small firmware-style function** that copies a sensor reading into a fixed buffer (e.g., `char buf[16]`). Use `snprintf(buf, sizeof(buf), "%d", sensor_value)` and verify that even with a large sensor value, the buffer never overflows.

## Next Up

Tomorrow: **Integer Overflows & Underflows in Firmware Arithmetic** — how wrapping a `uint16_t` counter or misusing signed/unsigned arithmetic can silently corrupt control loops, sensor fusion, and even trigger buffer overflows in embedded systems. We'll look at real-world examples from IoT firmware and how to catch them with static analysis.
