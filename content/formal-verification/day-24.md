---
title: "Day 24: MISRA C 2012: Rules, Deviations & Compliance Reports"
date: 2026-07-06
tags: ["til", "formal-verification", "misra-c", "rules", "deviations"]
---

## What I Explored Today

Today I dug into the practical mechanics of MISRA C:2012 compliance — not just the rule book, but how you actually enforce, deviate, and report against it in a real embedded project. I focused on the three pillars: understanding rule categories (Mandatory, Required, Advisory), writing formal deviation records, and generating compliance reports that auditors actually accept. The key insight: MISRA is a process, not a checklist, and the compliance report is the artifact that proves you followed that process.

## The Core Concept

MISRA C:2012 defines 143 rules (plus 14 directives) organized into three categories. **Mandatory** rules (16 total) must never be violated — no deviation allowed. **Required** rules (109 total) must be followed unless you have a formally documented deviation. **Advisory** rules (18 total) are best practices; you should follow them, but you don’t need a written deviation if you don’t.

The real engineering work isn’t in fixing every violation — it’s in deciding which violations are acceptable and documenting why. A deviation isn’t a free pass; it’s a risk assessment. You must prove the violation is safe, unavoidable, or that the rule doesn’t apply in that context. The compliance report then aggregates all rules, violations, and deviations into a single document that proves your codebase is MISRA-compliant (or at least has a known, auditable risk profile).

## Key Commands / Configuration / Code

I used **Cppcheck** with the MISRA add-on and **PC-lint** for cross-validation. Here’s the setup and a real deviation example.

### Cppcheck with MISRA Add-on

```bash
# Install cppcheck and misra addon (Ubuntu/Debian)
sudo apt install cppcheck
# The misra.py addon ships with cppcheck >= 2.9
cppcheck --addon=misra.py --suppress=*:test/* --suppress=*:build/* \
         --suppress=misra-config --inline-suppr \
         --std=c99 --language=c src/ 2> misra_report.txt
```

The `--suppress=misra-config` flag hides configuration warnings (e.g., missing header paths). The `--inline-suppr` flag allows you to suppress specific violations inline with comments.

### Inline Suppression (for deviations)

```c
/* cppcheck-suppress [misra-c2012-10.3] */
/* Deviation: Cast from uint32_t to uint16_t is safe here because
   the value is guaranteed < 65536 by prior bounds check (line 42) */
uint16_t result = (uint16_t)some_32bit_value;
```

This is a **Required** rule (10.3: "The value of an expression shall not be assigned to a wider essential type"). The inline comment documents the deviation reason and references the bounds check.

### Formal Deviation Record (for Required rules)

When you can’t suppress inline (e.g., a function-level violation), you need a formal deviation record. Here’s a minimal template:

```markdown
## Deviation Record: DR-2026-007
**Rule:** MISRA C:2012 Required Rule 11.3
**Violation:** Cast between pointer to object and integer type
**File:** src/hal/spi.c, line 88
**Code:** `uint32_t addr = (uint32_t)&spi_regs->tx_buffer;`
**Justification:** Hardware register addresses are memory-mapped at fixed
  physical addresses. The cast is required to pass the address to the DMA
  controller which expects a 32-bit integer. No arithmetic is performed
  on the integer representation. This is a target-specific hardware access
  pattern and cannot be avoided.
**Risk Assessment:** Low — the cast is read-only and the resulting integer
  is only used as an argument to a hardware-specific function.
**Reviewer:** J. Smith (2026-07-06)
```

### Generating a Compliance Report with PC-lint

```bash
# PC-lint Plus command for MISRA C:2012 compliance report
lint-nt -u -std=c99 +misra(2012,required) \
        -i"C:\tools\pclp\include" \
        -i"src\include" \
        -report_total(compliance) \
        src/*.c > compliance_report.txt
```

The `-report_total(compliance)` flag generates a summary with:
- Total rules checked
- Number of violations per rule
- Number of deviations (inline suppressions + formal records)
- Compliance percentage (violations + deviations / total rules)

## Common Pitfalls & Gotchas

1. **Deviation records must be traceable.** If your inline suppression doesn’t reference a formal deviation ID, an auditor will reject it. Always pair `cppcheck-suppress` with a comment that includes a deviation number or a link to your deviation database.

2. **Advisory rules are not optional for compliance.** While you don’t need a written deviation, many certification bodies (e.g., ISO 26262, DO-178C) require you to document why you chose not to follow an advisory rule. Treat them as “Required with lighter paperwork.”

3. **Tool chains disagree on rule interpretations.** I found that Cppcheck’s MISRA add-on flags Rule 10.1 (operand type restrictions) more aggressively than PC-lint. Always cross-validate with at least two tools, and document which tool’s interpretation you’re following in your compliance report.

## Try It Yourself

1. **Run Cppcheck with MISRA on your own project.** Use the command above, then identify one Required rule violation. Write a formal deviation record for it using the template provided. Ensure the justification includes a risk assessment and a reviewer signature.

2. **Compare tool outputs.** Run both Cppcheck and PC-lint (or a free alternative like `misra-checker` from GitHub) on the same file. List at least two rules where the tools disagree. Document which interpretation you accept and why.

3. **Generate a compliance report.** Using either tool, produce a compliance report that shows the total number of rules checked, violations found, and deviations granted. Calculate your compliance percentage. If it’s below 100%, write a summary paragraph explaining the risk posture.

## Next Up

Tomorrow, I’m diving into **Frama-C Architecture: Plugins, ACSL & Value Analysis** — the static analysis powerhouse that goes beyond MISRA to prove functional correctness. We’ll look at how ACSL annotations drive the value analysis plugin and how to chain plugins for deep verification.
