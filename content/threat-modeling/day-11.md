---
title: "Day 11: Format String & Injection Vulnerabilities in Embedded C"
date: 2026-07-11
tags: ["til", "threat-modeling", "format-string", "injection"]
---

## What I Explored Today

Today I dove into format string vulnerabilities — a class of bugs that feels almost too easy to exploit, yet remains disturbingly common in embedded firmware. I spent the morning crafting a vulnerable UART command parser, then systematically broke it using `%x`, `%s`, and `%n` format specifiers to leak stack data and write arbitrary memory. The core insight: when user-controlled data is passed directly as the format argument to `printf`-family functions, the attacker gains read and write access to the entire process address space. On a Cortex-M4 without an MPU, that means full device control.

## The Core Concept

Format string vulnerabilities are not about buffer overflows. They exploit the variable-argument mechanism of the C calling convention. When you call `printf(user_input)`, the compiler generates code that pushes arguments onto the stack, then the `printf` implementation walks the stack looking for format specifiers. If you pass `"%x %x %x %x"`, `printf` will pop four words from the stack and print them as hex — regardless of whether you intended to pass those values.

The real danger comes from `%n`. This specifier writes the number of characters printed so far to an `int*` argument. If an attacker can control the format string, they can chain `%n` with positional specifiers like `%1$n` to write arbitrary values to arbitrary addresses. In embedded systems, this means overwriting function pointers in RAM, modifying interrupt vector tables, or patching security checks at runtime.

Why does this matter for embedded? Because we often log debug messages over UART, USB CDC, or even BLE. A single `printf(buffer)` in a command handler — where `buffer` contains user input — turns your debug interface into a weapon. No ASLR, no stack canaries, no W^X on most MCUs. The attack surface is enormous.

## Key Commands / Configuration / Code

Here's a realistic vulnerable UART command handler for an STM32 or similar MCU:

```c
// Vulnerable: user input passed directly to printf
void uart_cmd_handler(char *cmd_buffer, uint16_t len) {
    // cmd_buffer comes from DMA UART RX, null-terminated
    printf(cmd_buffer);  // BUG: format string injection
}
```

An attacker at the serial terminal sends:
```
%x.%x.%x.%x.%x
```
And gets back leaked stack data, including return addresses and local variables.

Now the exploit — writing to an arbitrary address using `%n`:

```c
// Attacker sends: \x34\x12\x00\x20%10x%7$n
// This writes 0x0A (10 chars printed) to address 0x20001234
// The %7$n targets the 7th argument position (where our address sits on stack)
```

To defend, always use the format string as a literal:

```c
// Safe: format is a compile-time constant
void uart_cmd_handler_safe(char *cmd_buffer, uint16_t len) {
    printf("%s", cmd_buffer);  // OK: user data is an argument, not the format
}
```

For systems where `printf` is too heavy, the same applies to `snprintf`, `fprintf`, `sprintf`, and even custom `vprintf`-style loggers:

```c
// Also vulnerable
void log_debug(const char *msg) {
    char buf[128];
    snprintf(buf, sizeof(buf), msg);  // BUG: msg is format string
    uart_send(buf);
}

// Safe
void log_debug_safe(const char *msg) {
    char buf[128];
    snprintf(buf, sizeof(buf), "%s", msg);  // OK
    uart_send(buf);
}
```

Static analysis catches this. Run `cppcheck --enable=all` or use GCC's `-Wformat-security`:

```bash
arm-none-eabi-gcc -Wformat -Wformat-security -Werror=format-security main.c
```

This flags any non-literal format string. Make it a hard error in your CI.

## Common Pitfalls & Gotchas

**1. Thinking "I only use snprintf, so I'm safe"**  
`snprintf` limits output length but still interprets format specifiers. The `%n` write still works. Buffer size doesn't prevent arbitrary memory write — it only limits how many characters are printed before the write.

**2. Forgetting about custom loggers and assertion macros**  
Many embedded projects wrap `printf` in macros like `DEBUG_PRINT(fmt, ...)`. If the macro expands to `printf(fmt, ##__VA_ARGS__)` and someone calls `DEBUG_PRINT(user_str)`, the vulnerability is back. Always force the format argument to be a string literal, or use `"%s"` as the format.

**3. Assuming "nobody will send %n over UART"**  
On a production device, an attacker with physical access or a compromised BLE/OTA update channel can send arbitrary bytes. `%n` is just ASCII. A simple `printf(buffer)` in a bootloader menu or diagnostic shell is a full code execution primitive. I've seen this in production medical devices.

## Try It Yourself

1. **Leak the stack** — Write a minimal STM32 project that echoes UART input via `printf(buffer)`. Send `%08x.%08x.%08x.%08x` and observe leaked addresses. Identify which leaked value is the return address of the calling function.

2. **Write to a known address** — Place a global variable `volatile int canary = 0xDEAD;` in RAM. Using `%n` in your format string, overwrite `canary` to `0x0001`. You'll need to pad the output with `%<N>x` to control the character count. Verify with a debugger.

3. **Harden your codebase** — Run `grep -rn 'printf(' src/ | grep -v '"'` on your embedded project. Find every call where the format string is not a literal. Refactor each one to use `printf("%s", ...)` or `puts()`. Add `-Wformat-security` to your build flags and fix all warnings.

## Next Up

Tomorrow: **Use-After-Free & Memory Corruption in Bare-Metal Systems**. We'll explore how dynamic memory allocators on MCUs become attack surfaces, why a freed buffer can still hold a function pointer, and how to implement a simple memory guard to catch UAF at runtime.
