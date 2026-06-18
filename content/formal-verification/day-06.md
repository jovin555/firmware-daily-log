---
title: "Day 06: MISRA C 2012: Rules, Deviations & Compliance Reports"
date: 2026-06-18
tags: ["til", "formal-verification", "misra-c", "rules", "deviations"]
---

## What I Explored Today

Today I dug into the practical mechanics of MISRA C:2012 — not just the rule book, but how to actually enforce it, document deviations, and generate compliance reports that auditors will accept. I’ve seen too many projects where “MISRA compliance” means running a checker once and ignoring the warnings. Real compliance requires a traceable, auditable process: rule selection, deviation handling, and a final compliance report that proves each rule was either obeyed or explicitly justified.

## The Core Concept

MISRA C:2012 defines 143 rules (plus 16 directives) categorized into three mandatory levels: **Required**, **Advisory**, and **Mandatory**. The key insight is that MISRA is not a coding standard you “pass” — it’s a risk management framework. You decide which rules apply to your project, document why you deviate from any rule, and produce a compliance report that shows the audit trail.

The compliance workflow has three phases:
1. **Rule selection** — Choose which rules are mandatory for your project (typically all Required + Mandatory, Advisory are optional)
2. **Static analysis** — Run a MISRA checker (e.g., PC-lint, Coverity, or open-source tools like cppcheck with MISRA addon)
3. **Deviation management** — For every rule violation you cannot or will not fix, write a formal deviation record

A **deviation** is not a free pass. It must include: the rule ID, the specific code location, the reason for deviation, and sign-off from a technical authority. Without this, your compliance report is worthless.

## Key Commands / Configuration / Code

### 1. Running cppcheck with MISRA addon (open-source approach)

```bash
# Install cppcheck with MISRA support (version 2.9+)
# On Ubuntu/Debian:
sudo apt install cppcheck

# Run MISRA C:2012 checks on a source file
cppcheck --addon=misra.py --suppress=misra-config \
  --suppress=unmatchedSuppression \
  --enable=all --inconclusive \
  --std=c99 \
  main.c 2> misra_report.txt

# The misra.py addon is bundled with cppcheck
# Output format: line: severity: rule ID: message
# Example output:
# main.c:12: style: misra violation (rule 8.2) [misra-c2012-8.2]
#   Function parameter 'size' has no type specified
```

### 2. MISRA deviation record template (JSON format for tooling)

```json
{
  "deviation_id": "DEV-2026-001",
  "rule_id": "MISRA-C:2012 Rule 10.1",
  "file": "src/driver/adc.c",
  "line": 47,
  "severity": "Required",
  "reason": "Operand of logical operator is volatile hardware register; value is inherently boolean but not _Bool type. Hardware spec guarantees only 0 or 1.",
  "justification": "Rule 10.1 forbids non-boolean operands in logical operators. This is a known hardware interface pattern. Deviation approved per project deviation policy.",
  "approved_by": "Jane Doe, Lead Engineer",
  "date": "2026-06-18"
}
```

### 3. Compliance report generation script (bash + awk)

```bash
#!/bin/bash
# generate_compliance_report.sh
# Assumes cppcheck output in misra_report.txt

echo "=== MISRA C:2012 Compliance Report ==="
echo "Project: firmware-v2.3"
echo "Date: $(date)"
echo ""

# Count violations by severity
echo "Violation Summary:"
grep -oP 'misra violation \(rule \K[^)]+' misra_report.txt | \
  sort | uniq -c | sort -rn | \
  awk '{printf "  Rule %s: %d violations\n", $2, $1}'

echo ""
echo "Deviation Records:"
# Count deviations from a separate deviations.json file
python3 -c "
import json
with open('deviations.json') as f:
    devs = json.load(f)
print(f'  Total deviations: {len(devs)}')
for d in devs:
    print(f'  {d[\"deviation_id\"]}: {d[\"rule_id\"]} at {d[\"file\"]}:{d[\"line\"]}')
"

echo ""
echo "Compliance Status:"
# If no violations remain after deviations, mark compliant
violations=$(grep -c 'misra violation' misra_report.txt)
echo "  Unresolved violations: $violations"
if [ "$violations" -eq 0 ]; then
    echo "  RESULT: COMPLIANT"
else
    echo "  RESULT: NON-COMPLIANT (resolve or deviate)"
fi
```

## Common Pitfalls & Gotchas

### 1. Confusing “Required” with “Mandatory”
Required rules must be followed unless a formal deviation exists. Mandatory rules *cannot* be deviated from — they are absolute. Many teams treat Required as optional, which fails audits. Always check the rule category before deciding to deviate.

### 2. Forgetting to suppress false positives properly
cppcheck and other tools generate false positives for MISRA rules (e.g., Rule 10.1 on hardware registers). The correct approach is to write a deviation, not to globally suppress the rule. A global suppression hides real violations. Use inline suppressions only for provably impossible cases:

```c
// cppcheck-suppress misra-c2012-10.1 // hardware register, only 0/1
if (HW_STATUS_REG & 0x01) {
    // ...
}
```

### 3. Treating the compliance report as a one-time artifact
Auditors expect the compliance report to be regenerated for every release, with a clear diff from the previous version. Automate the report generation in your CI pipeline. If you generate it manually, you will miss changes.

## Try It Yourself

1. **Run cppcheck with MISRA on a small C file** — Write a function that uses `int` for a boolean parameter (violates Rule 10.1). Run the check, observe the output, then write a deviation record for it.

2. **Create a compliance report script** — Take the bash script above and adapt it to your project. Add a step that compares the current violation count against the previous release’s count.

3. **Audit a legacy module** — Pick a 500-line C file from an old project. Run MISRA checks, categorize violations by rule ID, and decide which ones need deviations vs. fixes. Write at least two deviation records.

## Next Up

Tomorrow I’ll explore **Frama-C Architecture: Plugins, ACSL & Value Analysis** — how to move beyond syntactic checks and use formal specification to prove the absence of runtime errors. We’ll look at ACSL annotations, the Eva plugin for value analysis, and how to integrate Frama-C into a CI pipeline.
