---
title: "Day 13: MISRA C:2012: Rule Categories & Security Rationale"
date: 2026-07-13
tags: ["til", "threat-modeling", "misra-c"]
---

## What I Explored Today

Today I dug into the rule categorization system of MISRA C:2012 and mapped each category to concrete security threats. MISRA isn't just a style guide—it's a risk-mitigation framework. The 2012 edition organizes 143 rules into 21 categories (Directives and Rules), each with a clear security or safety rationale. I focused on understanding why a rule exists, not just what it prohibits, and how that maps to real-world embedded vulnerabilities like buffer overflows, race conditions, and undefined behavior exploits.

## The Core Concept

MISRA C:2012 categorizes rules by their enforcement mechanism and the type of risk they address. The two top-level divisions are **Directives** (advisory, require manual verification) and **Rules** (mandatory, checkable by static analysis). Rules are further split into **Required** (must be followed) and **Advisory** (strongly recommended).

The security rationale behind each category is straightforward: undefined behavior is the root of nearly all memory corruption exploits. MISRA forces you to write C in a way that eliminates undefined, unspecified, or implementation-defined behavior. For example, Rule 18.1 (pointer arithmetic only on array objects) directly prevents the classic "off-by-one" that leads to buffer overflows. Rule 12.1 (no implicit conversions that change signedness) prevents integer overflow attacks that bypass bounds checks.

The categories are not arbitrary. They map to specific threat model elements:
- **Category 1: Environment** (Directives 4.x) — addresses assumptions about the compiler and runtime that attackers could exploit.
- **Category 8: Declarations and Types** (Rules 8.x) — prevents type confusion and memory layout exploits.
- **Category 18: Pointers and Arrays** (Rules 18.x) — directly targets spatial memory safety.
- **Category 21: Preprocessing Directives** (Rules 21.x) — prevents macro injection and conditional compilation attacks.

The key insight: MISRA doesn't make your code "safe" in the security sense by itself. It makes your code *deterministic* under the C standard, which means a static analyzer can prove the absence of entire classes of vulnerabilities.

## Key Commands / Configuration / Code

Let's see how to enforce these categories with a real static analyzer. I'll use `cppcheck` with MISRA addon, which is free and widely available.

```bash
# Install cppcheck with MISRA support (Ubuntu/Debian)
sudo apt install cppcheck

# Run MISRA C:2012 checking on a source file
cppcheck --addon=misra --suppress=misra-c2012-21.1 \
  --suppress=misra-c2012-21.2 \
  --std=c99 --language=c \
  --enable=all --inconclusive \
  src/firmware.c 2> misra_report.txt
```

Here's a concrete example of a MISRA violation with security implications:

```c
/* Non-compliant: violates Rule 10.1 (operand type mismatch) 
   and Rule 12.1 (implicit conversion changes signedness) */
int16_t process_sensor(int16_t raw_value) {
    uint16_t scaled = raw_value * 2;  /* Implicit signed-to-unsigned conversion */
    return scaled / 10;               /* Potential overflow, undefined behavior */
}

/* Compliant: explicit casts, range checks, no implicit conversions */
int16_t process_sensor_safe(int16_t raw_value) {
    int32_t safe_temp = (int32_t)raw_value * 2;  /* Widen before multiply */
    
    /* Range check per Rule 14.3 (controlling expressions) */
    if ((safe_temp < INT16_MIN) || (safe_temp > INT16_MAX)) {
        return 0;  /* Clamp or error — prevents undefined behavior */
    }
    
    int16_t scaled = (int16_t)safe_temp;  /* Explicit cast per Rule 10.3 */
    int32_t result = (int32_t)scaled / 10;
    return (int16_t)result;
}
```

To enforce this in a CI pipeline, use a Makefile target:

```makefile
# MISRA compliance check target
.PHONY: misra-check
misra-check:
	cppcheck --addon=misra --suppress=misra-c2012-21.1 \
		--suppress=misra-c2012-21.2 \
		--std=c99 --language=c \
		--enable=all --inconclusive \
		--xml --xml-version=2 \
		src/ 2> misra_report.xml
	# Fail build if any Required rules violated
	@if grep -q 'severity="error"' misra_report.xml; then \
		echo "MISRA violations found!"; \
		exit 1; \
	fi
```

## Common Pitfalls & Gotchas

1. **Treating all MISRA rules as equally important for security.** Rule 4.1 (only use standard C features) is critical for portability but doesn't directly prevent exploits. Rule 18.4 (pointer subtraction only within same array) is a hard security boundary. Prioritize rules in categories 8, 12, 18, and 21 for security reviews.

2. **Suppressing rules without understanding the security rationale.** I've seen teams suppress Rule 10.1 (operand type mismatch) because "it's just a warning." That rule prevents integer promotions that can silently change signedness—exactly the kind of bug that leads to buffer overflows in memory-constrained systems. Always document *why* a suppression is safe.

3. **Assuming static analysis catches all violations.** MISRA Directives (like Dir 4.1) require manual review. A static analyzer can't verify that you've correctly analyzed all possible runtime paths for a directive. You need a process—code reviews, formal methods, or runtime assertions—to cover these.

## Try It Yourself

1. **Run cppcheck with MISRA on your current firmware project.** Use the command above. Count how many Required rules are violated. Pick the top three categories (e.g., 8, 12, 18) and fix one violation from each. Re-run to confirm.

2. **Map three MISRA rules to specific CVEs.** Find a public CVE in an embedded system (e.g., CVE-2021-3156 in sudo, or a known IoT buffer overflow). Identify which MISRA C:2012 rule would have prevented it. Write a one-paragraph security rationale for that rule.

3. **Write a MISRA-compliant version of a common pattern: a circular buffer.** Ensure you follow Rules 18.1 (pointer arithmetic only on array), 18.4 (pointer subtraction within same array), and 12.1 (no implicit signedness changes). Test with both valid and invalid inputs.

## Next Up

Tomorrow: **MISRA C++ & AUTOSAR C++14 for Safety-Critical Firmware** — how the C++ rules differ from C, why AUTOSAR adds 100+ additional guidelines, and how to handle templates, exceptions, and dynamic memory in a safety-critical context.
