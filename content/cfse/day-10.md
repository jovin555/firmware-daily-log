---
title: "Day 10: Safety Case: Goal Structuring Notation (GSN)"
date: 2026-06-22
tags: ["til", "cfse", "safety-case", "gsn", "goals"]
---

## What I Explored Today

Today I dove into Goal Structuring Notation (GSN) as the backbone of a structured safety case. After weeks of generating hazard logs and FMEA tables, I needed a way to connect the dots—to show *why* those analyses prove the system is acceptably safe. GSN is the diagrammatic language that makes a safety case auditable, defensible, and—most importantly—comprehensible to a certification authority like the TÜV or FAA. I built my first GSN model for a simple electronic throttle control, and the clarity it brought was immediate.

## The Core Concept

A safety case is a structured argument, supported by evidence, that a system is acceptably safe. Without a formal notation, safety cases devolve into walls of text where assumptions are buried and evidence is scattered. GSN solves this by forcing the engineer to decompose a top-level safety goal into sub-goals, each supported by evidence (solutions), and each connected by explicit reasoning (strategies). The "why" behind GSN is traceability: an assessor must be able to follow the argument from "the system is safe" down to "here is the test report proving the fault detection time is 10 ms." GSN also makes implicit assumptions visible—those "context" nodes that everyone assumes but nobody writes down until the auditor asks.

In practice, GSN is not just a drawing tool. It's a reasoning discipline. Every time you add a goal, you must ask: "What would disprove this?" That question drives you to add context, justification, or additional sub-goals. The result is a safety case that survives a real audit.

## Key Commands / Configuration / Code

I use the open-source `gsn-lib` LaTeX package (by Tim Kelly and Rob Weaver) to generate publication-quality GSN diagrams. Below is a minimal example for a throttle-override safety goal.

```latex
% preamble.tex — requires gsn-lib.sty
\documentclass{standalone}
\usepackage{gsn}
\begin{document}

% Define the top goal
\gsngoal{top}{The electronic throttle control (ETC) system shall prevent unintended acceleration above 10\% pedal position when brake is applied.}

% Define context — the system boundary
\gsncontext{ctx1}{ETC system includes: pedal sensor, ECU, throttle actuator, brake switch.}

% Define strategy — how we decompose the goal
\gsnstrategy{strat1}{Argument over all credible single-point failures in the ETC sensor chain.}

% Define sub-goals
\gsngoal{g1}{Pedal sensor failure (stuck high) is detected within 10 ms.}
\gsngoal{g2}{Brake switch failure (stuck open) does not prevent throttle cut.}

% Define solutions — the evidence
\gsnsolution{sol1}{Fault injection test report: sensor failure detection time = 8.2 ms (pass).}
\gsnsolution{sol2}{FMEDA analysis: brake switch failure rate = 0.1 FIT, diagnostic coverage = 99\%.}

% Build the tree
\gsntree{top}{
    \gsncontext{ctx1} -- \gsnarrow{top};
    \gsnstrategy{strat1} -- \gsnarrow{top};
    \gsngoal{g1} -- \gsnarrow{strat1};
    \gsngoal{g2} -- \gsnarrow{strat1};
    \gsnsolution{sol1} -- \gsnarrow{g1};
    \gsnsolution{sol2} -- \gsnarrow{g2};
}

\end{document}
```

Compile with `pdflatex gsn_example.tex`. The output is a clean, standards-compliant GSN diagram with rounded rectangles for goals, parallelograms for context, and underlines for solutions.

For a more interactive approach, I also use the **Adelard ASCE** tool (commercial, but has a free viewer). The key command in ASCE is:

```
// Add a goal node
add goal "G1" text="Pedal sensor failure detected within 10 ms" status="claimed"
// Add a solution node
add solution "Sn1" text="Fault injection test report v2.1" reference="doc/ETC_FIT_2026.pdf"
// Link them
link "G1" to "Sn1" type="supportedBy"
```

## Common Pitfalls & Gotchas

1. **Confusing goals with solutions.** A goal is a claim (e.g., "The system detects the fault"). A solution is evidence (e.g., "Test report shows detection time = 8 ms"). I've seen engineers put test data directly into a goal node. That breaks the argument structure—you lose the ability to ask "what if the test was flawed?" Always keep claims and evidence separate.

2. **Missing context nodes.** The most common audit finding is an unstated assumption. For example, you might claim "fault detection time < 10 ms" without noting that this applies only when the ECU clock is within tolerance. Add a context node: "Assumes ECU clock drift < 2% per ISO 26262-5." Without it, an assessor will flag the argument as incomplete.

3. **Over-connecting strategies.** A strategy node should decompose one goal into multiple sub-goals. I've seen diagrams where a strategy connects to five different goals from different branches, creating a spiderweb. Keep the tree hierarchical: one strategy per decomposition step. If you need to combine arguments, use an "undeveloped" goal with a justification node instead.

## Try It Yourself

1. **Build a GSN fragment for a watchdog timer.** Create a top goal: "Watchdog timer resets the MCU within 100 ms of software hang." Add a context node for the watchdog timeout period. Then decompose into sub-goals: (a) watchdog clock is accurate, (b) reset line is not masked by hardware fault. Attach a solution (e.g., oscilloscope capture) to each sub-goal.

2. **Audit an existing safety argument.** Take a hazard from your current project (e.g., "Overvoltage on sensor input does not cause runaway"). Write it as a GSN goal. Then ask: what evidence do you actually have? If you can't find a solution node, you've found a gap in your safety case.

3. **Convert a textual safety case to GSN.** Find a paragraph from a safety manual (e.g., "The system uses dual-channel comparison to detect faults"). Draw the GSN tree: top goal → strategy (argument over channel mismatch) → sub-goals (channel A works, channel B works, comparator works) → solutions (test reports, FMEDA). This exercise exposes hidden assumptions immediately.

## Next Up

Tomorrow: **Software Safety Requirements: Deriving from Hazards**. We'll take the hazard log from Day 3 and trace each hazardous event down to a concrete, verifiable software requirement—using ASIL decomposition and safety mechanisms like E2E protection and memory partitioning. Bring your hazard analysis and a copy of ISO 26262-6.
