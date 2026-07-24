---
title: "Day 15: 8D Reports: Writing for Customers & Auditors"
date: 2026-07-24
tags: ["til", "fmea-rca", "8d-report", "documentation"]
---

## What I Explored Today

Today I dug into the painful reality of 8D report writing—not the theory, but the actual mechanics of producing a document that satisfies both a demanding customer quality engineer and a third-party auditor. After spending hours reviewing rejected reports from a Tier-1 automotive supplier, I realized the gap isn't technical knowledge; it's knowing how to structure evidence so that a reader who wasn't in the room can independently verify every claim. We covered the difference between a "good enough" internal report and a "defensible" external deliverable, including specific formatting rules, traceability requirements, and the exact language that triggers auditor red flags.

## The Core Concept

An 8D report for a customer or auditor is not a problem-solving document—it is a forensic evidence package. The fundamental shift is from "what we did" to "what we proved." Every containment action must have a timestamped photo or log entry. Every root cause must cite a specific test result or data point. Every permanent corrective action must reference a changed work instruction revision number.

The reason this matters: auditors and customer quality engineers do not trust your narrative. They trust your data trail. If you write "We replaced the faulty sensor," they will ask: "Which sensor? What was the serial number? What test showed it was faulty? Who authorized the replacement? What is the new sensor's calibration certificate?" Your report must pre-answer these questions in a way that requires zero follow-up.

The golden rule: **Every claim in D4 (Root Cause Analysis) must have a corresponding evidence artifact referenced in D5 (Permanent Corrective Actions) or D6 (Implementation & Validation).** If you claim "oxide contamination caused the bond failure," your D5 must list the SEM/EDX analysis report number and the revised cleaning process spec.

## Key Commands / Configuration / Code

Here is the actual template structure I now use for customer-facing 8D reports. This is not a generic form—it's a LaTeX-based document with embedded version control and mandatory cross-references.

```latex
% 8D_Report_Template.tex
% Compile with: pdflatex -shell-escape 8D_Report_Template.tex
% Requires: hyperref, xcolor, datatool, etoolbox

\documentclass[11pt]{article}
\usepackage[colorlinks=true,linkcolor=blue]{hyperref}
\usepackage{datatool} % For data validation tables

% Define mandatory fields - report will not compile if empty
\newcommand{\ReportID}{8D-2026-0715-A}
\newcommand{\CustomerPO}{PO-98765}
\newcommand{\DefectPartNumber}{PWB-3421-RevC}
\newcommand{\DateOpened}{2026-07-15}
\newcommand{\DateClosed}{2026-07-24}

\begin{document}

\section*{D4: Root Cause Analysis}
% MANDATORY: Each root cause must link to a test report
\subsection*{Root Cause 1: Solder voiding >30\% in BGA-12}
\textbf{Evidence:} X-ray inspection report \href{run:./evidence/XRAY_20260715.pdf}{XR-20260715-003} \\
\textbf{Statistical significance:} p-value = 0.003 (Mann-Whitney U test, n=50) \\
\textbf{Mechanism:} Reflow profile peak temperature 217°C vs. spec 230-245°C \\
\textbf{Linked D5 Action:} \hyperref[sec:d5]{Reflow profile update (see D5, Action \#4)}

\section*{D5: Permanent Corrective Actions}
\label{sec:d5}
\begin{enumerate}
    \item \textbf{Action \#4: Reflow profile revision} 
    \begin{itemize}
        \item Old spec: \texttt{PROFILE\_REV\_3.2} (peak 217°C)
        \item New spec: \texttt{PROFILE\_REV\_4.0} (peak 235°C ±3°C)
        \item Implementation date: 2026-07-20
        \item Verification: 24-hour burn-in of 100 units, zero failures
        \item Document change: ECO-2026-0718, \href{run:./evidence/ECO_20260718.pdf}{link}
    \end{itemize}
\end{enumerate}

\end{document}
```

For the mandatory evidence index, I use a simple CSV-based validation script:

```bash
#!/bin/bash
# validate_8d_evidence.sh
# Usage: ./validate_8d_evidence.sh <report_id>
# Checks that every claim in D4 has a corresponding file in evidence/

REPORT_ID=${1:-"8D-2026-0715-A"}
EVIDENCE_DIR="./evidence"
CLAIMS_FILE="./claims_${REPORT_ID}.txt"

echo "=== Evidence Validation for ${REPORT_ID} ==="

# Extract all \href{run:...} references from the LaTeX source
grep -oP 'run:\./evidence/\K[^}]+' "${REPORT_ID}.tex" | sort -u > /tmp/required_evidence.txt

missing_count=0
while IFS= read -r file; do
    if [ ! -f "${EVIDENCE_DIR}/${file}" ]; then
        echo "MISSING: ${file}"
        ((missing_count++))
    fi
done < /tmp/required_evidence.txt

if [ ${missing_count} -eq 0 ]; then
    echo "PASS: All evidence files present."
else
    echo "FAIL: ${missing_count} evidence file(s) missing."
    exit 1
fi
```

## Common Pitfalls & Gotchas

**1. The "We Fixed It" Narrative Trap**
Never write "We replaced the component and the problem went away." That is correlation, not causation. An auditor will immediately flag this. Instead, write: "We replaced component U7 (serial 22A3B) with a known-good unit (serial 44C1D) from a different lot. The failure rate dropped from 12% to 0% over 500 cycles (p<0.001). Subsequent XRF analysis of the failed U7 showed tin-lead ratio of 60:40 vs. spec 63:37 (see report XRF-20260716)." The difference is the inclusion of the control group and the analytical evidence.

**2. Orphaned Containment Actions**
A common audit finding: D3 (Interim Containment) actions that are never formally closed or transitioned to D5. If you implemented 100% inspection at the customer's site, your D6 must show the date that inspection was removed and replaced by the process change. I've seen reports where containment ran for 18 months because nobody wrote the removal date. Always include a "Containment Removal Criteria" subsection in D3.

**3. Version Control Amnesia**
Every document reference must include a revision letter or date. "Per the reflow profile spec" is useless. "Per PROFILE_REV_4.0, approved 2026-07-20" is auditable. I use a simple rule: if you can't point to a specific file name and revision, it doesn't exist in the audit trail.

## Try It Yourself

1. **Audit your last 8D report**: Open your most recent customer-facing 8D. For every sentence in D4, highlight it in yellow. Then find the corresponding evidence file or document reference. If more than 20% of sentences have no link, rewrite the report using the LaTeX template above.

2. **Build the evidence validation script**: Create a directory `./evidence` and populate it with 5 dummy PDF files (use `touch`). Write a claims file with 3 evidence references. Run the validation script. Then delete one file and confirm the script catches it.

3. **Rewrite a "narrative" paragraph**: Take this weak statement: "We found that the connector was not fully seated due to operator error." Rewrite it as an auditable claim with: (a) the specific connector part number, (b) the measurement that proved incomplete seating (e.g., pull test force < 5N vs. spec 15N), (c) the operator training record number, and (d) the revised assembly instruction revision.

## Next Up

Tomorrow: **Common RCA Anti-Patterns: Stopping at the First Plausible Cause** — why the first root cause you find is almost never the real one, and how to force yourself to keep digging until you hit the systemic failure.
