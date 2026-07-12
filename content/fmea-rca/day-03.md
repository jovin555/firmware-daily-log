---
title: "Day 03: D1-D2: Forming a Team & Defining the Problem Precisely"
date: 2026-07-12
tags: ["til", "fmea-rca", "d1", "d2", "problem-definition"]
---

## What I Explored Today

Yesterday we laid out the 8D landscape. Today I dug into the first two gates that separate a chaotic firefight from a structured investigation: D1 (Team Formation) and D2 (Problem Definition). In embedded systems, I’ve seen too many root cause analyses fail because the wrong people were in the room, or because the problem statement was a vague complaint like “the sensor glitches sometimes.” D1 and D2 are where you decide who holds the wrenches and what exactly you’re fixing. I spent the morning reviewing a real case from a past project—a CAN bus timeout on a production line—and mapped how a proper D1/D2 would have saved us three weeks of wild goose chases.

## The Core Concept

D1 is not just “get some people together.” It’s a deliberate selection of cross-functional expertise with a clear charter. In embedded systems, that means you need at least: a hardware engineer (to own signal integrity and power), a firmware engineer (to own state machines and timing), a test engineer (to own the reproduction setup), and a quality engineer (to own the process and documentation). The team leader must be empowered to escalate, not just a junior engineer handed a problem they can’t fix.

D2 is where most investigations derail. A precise problem definition must answer five questions: **What** is the defect? **Where** does it appear (geographic, system, submodule)? **When** does it happen (time, temperature, firmware version, serial number range)? **How big** is the impact (frequency, severity, cost)? **How repeatable** is it? In embedded, the “when” often includes environmental conditions—voltage rail ripple, ambient temperature, or even the phase of the moon (I’m only half joking about EMI from nearby machinery). A good D2 statement reads like a bug report that a test engineer could reproduce blindfolded.

## Key Commands / Configuration / Code

Here’s a practical checklist I use for D1 team formation, and a template for D2 that I paste into every ticket.

### D1 Team Charter Template (Markdown)
```markdown
# D1 Team Charter: CAN Bus Timeout on Line 7

## Team Members
- **Team Leader**: Sarah K. (Sr. Systems Engineer) — escalation to VP Eng
- **Hardware**: Mike R. (HW Design) — owns PHY layer, terminations
- **Firmware**: Ana L. (FW Lead) — owns CAN driver, error handling
- **Test**: James T. (Test Automation) — owns reproduction harness
- **Quality**: Priya S. (QE) — owns documentation, containment actions

## Charter
- Goal: Identify root cause of sporadic CAN bus timeout on assembly line 7
- Authority: Full access to test logs, schematics, source code
- Constraints: Must provide interim containment within 48 hours
- Meeting cadence: Daily standup at 09:00, 15 min max
```

### D2 Problem Definition Template (Python script to generate structured fields)
```python
#!/usr/bin/env python3
"""
d2_problem_definition.py — Generate a structured D2 problem statement.
Usage: ./d2_problem_definition.py --defect "CAN timeout" --where "Line 7, station 3" \
    --when "FW v2.1.0, temp > 40C" --impact "5% of units, 2 sec delay" \
    --repeatable "3/10 attempts with thermal chamber at 50C"
"""
import argparse

def generate_d2(args):
    print("=" * 60)
    print("D2 PROBLEM DEFINITION")
    print("=" * 60)
    print(f"Defect:       {args.defect}")
    print(f"Where:        {args.where}")
    print(f"When:         {args.when}")
    print(f"Impact:       {args.impact}")
    print(f"Repeatable:   {args.repeatable}")
    print("-" * 60)
    print("Problem Statement:")
    print(f"  The system exhibits {args.defect} at {args.where} "
          f"under conditions: {args.when}. "
          f"Impact is {args.impact}. "
          f"Reproducibility: {args.repeatable}.")
    print("=" * 60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--defect", required=True)
    parser.add_argument("--where", required=True)
    parser.add_argument("--when", required=True)
    parser.add_argument("--impact", required=True)
    parser.add_argument("--repeatable", required=True)
    args = parser.parse_args()
    generate_d2(args)
```

### Example invocation and output
```bash
$ python d2_problem_definition.py \
    --defect "CAN bus timeout (error passive)" \
    --where "Assembly line 7, station 3, connector J5" \
    --when "FW v2.1.0, ambient temp > 40°C, bus load > 60%" \
    --impact "5% of units fail end-of-line test, 2-second delay per timeout" \
    --repeatable "3/10 attempts with thermal chamber at 50°C, 500 kbps"

============================================================
D2 PROBLEM DEFINITION
============================================================
Defect:       CAN bus timeout (error passive)
Where:        Assembly line 7, station 3, connector J5
When:         FW v2.1.0, ambient temp > 40°C, bus load > 60%
Impact:       5% of units fail end-of-line test, 2-second delay per timeout
Repeatable:   3/10 attempts with thermal chamber at 50°C, 500 kbps
------------------------------------------------------------
Problem Statement:
  The system exhibits CAN bus timeout (error passive) at Assembly line 7, station 3, connector J5 under conditions: FW v2.1.0, ambient temp > 40°C, bus load > 60%. Impact is 5% of units fail end-of-line test, 2-second delay per timeout. Reproducibility: 3/10 attempts with thermal chamber at 50°C, 500 kbps.
============================================================
```

## Common Pitfalls & Gotchas

1. **The “Hero” team**: You pick only firmware engineers because “it’s a software problem.” In embedded, most bugs are at the hardware-software boundary. Missing a hardware or test engineer means you’ll chase ghosts for weeks. Always include at least one person who can probe a scope and one who can read a schematic.

2. **Vague problem statements**: “The device crashes randomly” is not a D2. It’s a complaint. A proper D2 includes the exact firmware version, the power supply voltage at the time, the temperature range, and the serial number range. I’ve seen teams spend a month on a problem that was only reproducible with a specific batch of capacitors. The D2 would have caught that in one meeting.

3. **Skipping repeatability quantification**: If you can’t reproduce the issue in a controlled environment, you don’t have a problem—you have a rumor. D2 must include a reproduction rate (e.g., “3 out of 10 attempts”) and the exact setup. Without that, you can’t verify containment actions or root cause fixes later.

## Try It Yourself

1. **Form a D1 team for a past failure**: Think of a bug you encountered last month. Write a D1 charter with real names (or roles) and a clear charter. Did you have the right people? If not, who was missing?

2. **Rewrite a vague problem statement**: Take a ticket from your backlog that says “System intermittently fails.” Use the D2 template above to fill in the five fields. If you can’t fill in “When” or “Repeatable,” you know what to do next.

3. **Run the D2 script on your own data**: Clone the Python script, modify the argparse defaults to match your project’s naming conventions, and generate a problem statement for a current issue. Paste it into your bug tracker and see if it survives peer review.

## Next Up

Tomorrow: **D3 — Interim Containment Actions**. Once you know who’s on the team and what the problem is, you need to stop the bleeding. We’ll cover how to design a containment action that doesn’t break the production line, how to verify it works, and the difference between containment and corrective action. Bring your worst “band-aid” stories.
