---
title: "Day 17: FMEA Software Tools: APIS IQ-FMEA & Excel Templates"
date: 2026-07-28
tags: ["til", "fmea", "tools", "apis-iq-fmea"]
---

## What I Explored Today

Today I went deep on two ends of the FMEA tooling spectrum: APIS IQ-FMEA (the industry-standard commercial suite for structured FMEA management) and the humble-but-ubiquitous Excel template. I’ve used both in production environments—Excel for quick-turn DFMEAs on prototype boards, IQ-FMEA for PFMEAs on automotive transmission lines where traceability is audited by TÜV. The gap in capability is enormous, but so is the gap in adoption friction. Let’s break down what each tool actually does, how to configure them, and where they break.

## The Core Concept

FMEA software isn’t just a digital form. The core value is **relationship management**—linking functions, failure modes, effects, causes, controls, and actions across a multi-level system hierarchy. A spreadsheet can store rows; a proper tool like IQ-FMEA enforces a data model with referential integrity, version control, and audit trails.

Why does this matter? In a PFMEA for a battery pack assembly line, a single “failure mode” (e.g., “cell misalignment”) might have five causes (fixture wear, vision system drift, operator error, thermal expansion, debris) and three effects (short circuit, capacity loss, thermal runaway). Excel can list them, but IQ-FMEA can trace the cause back to a specific process step and the effect forward to a severity rating that propagates from a linked DFMEA. That cross-document linkage is the difference between a static table and a living risk model.

The trade-off: IQ-FMEA requires a license (€2k–€5k per seat), a learning curve (2–4 weeks for fluency), and discipline in data entry. Excel is free, familiar, and fragile—one accidental sort and your RPNs are orphaned.

## Key Commands / Configuration / Code

### 1. APIS IQ-FMEA: Creating a Structure Tree

In IQ-FMEA, the first step is defining the system hierarchy. This is not optional—the tool enforces a parent-child structure.

```
// In the "Structure" tab:
// Right-click root node -> "New Element"
// Element Type: "System" (for top-level)
// Element Type: "Function" (for functional decomposition)
// Element Type: "Component" (for hardware items)

// Example hierarchy for a DC-DC converter PFMEA:
// System: "12V-48V DC-DC Converter"
//   ├─ Function: "Regulate output voltage"
//   │    ├─ Component: "MOSFET Q1"
//   │    └─ Component: "Inductor L1"
//   └─ Function: "Thermal management"
//        └─ Component: "Heatsink assembly"
```

**Critical configuration**: Under `Tools > Options > FMEA Settings`, set `Severity / Occurrence / Detection` scales to match your company standard (e.g., 1–10 for automotive AIAG/VDA). IQ-FMEA ships with default scales; if you import an Excel file with different scales, the tool will silently remap values, corrupting your RPNs.

### 2. Excel Template: Minimal Viable FMEA

Here’s a production-grade Excel template structure (no macros, just formulas). Create columns:

| A | B | C | D | E | F | G | H | I | J | K |
|---|---|---|---|---|---|---|---|---|---|---|
| ID | Function | Failure Mode | Effect | Sev | Cause | Occ | Current Control | Det | RPN | Action |

**Key formulas**:
- `RPN (K2) = E2 * G2 * J2` — but note: this is the traditional AIAG method. VDA uses Action Priority (AP) tables, not RPN. If you’re ISO 26262, RPN is discouraged; use Severity × Occurrence only.

**Conditional formatting for RPN thresholds**:
```
// Select column K, Home > Conditional Formatting > New Rule
// Rule: =K2>=100 → red fill
// Rule: =K2>=50 → yellow fill
// Rule: =K2<50 → green fill
```

**Data validation for Severity (column E)**:
```
Data > Data Validation > List
Source: 1,2,3,4,5,6,7,8,9,10
// Add a helper sheet with descriptions:
// 1: No effect
// 10: Safety/regulatory non-compliance
```

### 3. Export/Import Between Tools

IQ-FMEA can import Excel via a specific schema. The trick is the **header mapping**:

```
// In IQ-FMEA: File > Import > Excel
// Map columns:
// Excel "Failure Mode" -> IQ-FMEA "Failure Mode (FM)"
// Excel "Cause" -> IQ-FMEA "Cause (FC)"
// Excel "Sev" -> IQ-FMEA "Severity (S)"
// Critical: IQ-FMEA expects numeric values for S/O/D, not text like "High"
```

## Common Pitfalls & Gotchas

1. **Excel: Sorting destroys data integrity.** If you sort by RPN descending, the row relationships between function, cause, and effect are preserved visually, but any linked formulas (e.g., VLOOKUPs to a master list) break. Always use Excel Tables (Insert > Table) with structured references, and never sort manually—use filters instead.

2. **IQ-FMEA: Over-engineering the structure tree.** New users create 10-level hierarchies for a simple assembly. This makes the FMEA unreadable and slows the tool to a crawl. Rule of thumb: max 4 levels (System → Subsystem → Component → Function). Deeper than that, you’re doing a design review, not an FMEA.

3. **Both tools: Ignoring the “Action” column.** I’ve seen teams spend 40 hours filling out Severity/Occurrence/Detection and then leave the Action column blank. The entire point of FMEA is to drive risk reduction. In IQ-FMEA, use the “Action Management” module to assign owners and due dates. In Excel, add a column for “Status” with data validation: Not Started, In Progress, Verified.

## Try It Yourself

1. **Excel exercise**: Create a 10-row FMEA for a simple product (e.g., a USB-C cable). Use the formulas above. Then, intentionally sort by RPN descending and check if any of your conditional formatting rules still apply correctly. Fix the issue by converting your range to an Excel Table.

2. **IQ-FMEA exercise**: If you have access, create a two-level structure tree for a DC-DC converter. Add one function, one failure mode, one cause, and one effect. Then use the “Link to DFMEA” feature to import a severity from a linked DFMEA document. Observe how the severity propagates.

3. **Cross-tool exercise**: Export your Excel FMEA as CSV. In IQ-FMEA, attempt an import using the schema above. Note which columns fail to map and why. This is a common real-world task when migrating from legacy spreadsheets.

## Next Up

Tomorrow: **Integrating FMEA with ISO 26262 / IEC 61508 Hazard Analysis**. We’ll map FMEA failure modes to hazard events, reconcile Severity with ASIL/SIL levels, and show how IQ-FMEA’s “Hazard Analysis” module can generate a Hazard Log that satisfies functional safety auditors. Bring your safety manual.
