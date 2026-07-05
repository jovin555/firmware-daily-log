---
title: "Day 23: Audit Preparation: DHF, DMR & Device History Records"
date: 2026-07-05
tags: ["til", "iec62304", "audit", "dhf", "dmr"]
---

## What I Explored Today

Today I dug into the three record types that auditors will demand to see during any IEC 62304 certification or surveillance audit: the Design History File (DHF), the Device Master Record (DMR), and Device History Records (DHR). These aren't just paperwork exercises — they are the backbone of traceability from a software requirement all the way to the shipped unit. I spent the morning mapping our existing Git tags, release notes, and CI/CD artifacts to these three categories, and found several gaps that would have been painful during an audit.

## The Core Concept

The FDA's Quality System Regulation (21 CFR 820) and IEC 62304 both require that you maintain three distinct but interrelated sets of records. Confusing them is the fastest way to fail an audit.

**Design History File (DHF)** — This is the *story of how the device was designed*. It contains design plans, design inputs (requirements), design outputs (architecture, source code, unit tests), design reviews, verification results, and validation results. For software, this means the SOUP plan, the software development plan, the requirements specification, the architecture document, detailed design, unit test reports, integration test reports, and system test reports. The DHF is created during development and is essentially closed once the design is finalized.

**Device Master Record (DMR)** — This is the *recipe for building the device*. It includes the specifications, drawings, composition, and all procedures for production. For software, the DMR is your build configuration, the exact compiler version, the linker script, the checksums of all third-party libraries, the release notes, the installation instructions, and the labeling. The DMR is a living document that gets updated whenever you change how the device is built.

**Device History Record (DHR)** — This is the *birth certificate of each individual unit*. It proves that a specific unit was built according to the DMR. For software, this is typically the release tag in your version control system, the CI/CD pipeline log that shows the exact build command, the checksum of the binary, and the deployment record. If you ship software on physical media, the DHR includes the serial number of the media and the date it was programmed.

The key insight: auditors will ask for a specific DHR (e.g., "show me the records for unit serial number 42"), then trace that back to the DMR that was used to build it, and then trace the DMR back to the DHF to verify that the design was properly verified and validated. If any link is broken, you get a non-conformance.

## Key Commands / Configuration / Code

Here's how I structure our Git repository and CI/CD to automatically generate these records.

**Git tag naming convention for DMR and DHR linkage:**
```bash
# DMR tag — identifies the exact build recipe
git tag -a dmr-v2.1.0 -m "DMR: v2.1.0 — GCC 12.2, FreeRTOS 10.4.6, libcrypto 3.0.8"
# DHR tag — identifies a specific released unit
git tag -a dhr-v2.1.0-build42 -m "DHR: v2.1.0-build42 — sha256: a3f8b2c1..."
```

**CI/CD pipeline snippet (GitHub Actions) that generates DHR artifacts:**
```yaml
# .github/workflows/release.yml
jobs:
  build:
    runs-on: ubuntu-22.04
    steps:
      - uses: actions/checkout@v4
        with:
          ref: dmr-v2.1.0  # Build from the DMR tag
      - name: Build firmware
        run: |
          make clean
          make RELEASE=1
          sha256sum build/firmware.bin > build/firmware.sha256
      - name: Archive DHR artifacts
        uses: actions/upload-artifact@v4
        with:
          name: dhr-v2.1.0-build42
          path: |
            build/firmware.bin
            build/firmware.sha256
            build/compile_commands.json  # Exact compiler flags
```

**DHF document index (Markdown, stored in `docs/dhf/`):**
```markdown
# Design History File — Ventilator Firmware v2.1.0
## Documents
- [SDP] Software Development Plan (IEC 62304 §5.1)
- [SRS] Software Requirements Specification (§5.2)
- [SAS] Software Architecture Specification (§5.3)
- [SDD] Software Detailed Design (§5.4)
- [SUTP] Software Unit Test Plan (§5.5)
- [SUTR] Software Unit Test Report (§5.5)
- [SITP] Software Integration Test Plan (§5.6)
- [SITR] Software Integration Test Report (§5.6)
- [SSTP] Software System Test Plan (§5.7)
- [SSTR] Software System Test Report (§5.7)
- [SOUP] SOUP Plan & Risk Assessment (§7.1)
- [REVIEWS] Design Review Minutes (all phases)
```

## Common Pitfalls & Gotchas

**1. Treating the DMR as static.** I've seen teams create a DMR once and never update it. The DMR must reflect the *current* build process. If you upgrade your compiler from GCC 11 to GCC 12, the DMR must be updated. The auditor will check that the DHR for a unit built last week matches the DMR that was current at that time. Solution: version your DMR documents and keep a change log.

**2. Forgetting the DHR for software-only devices.** If you ship firmware that can be updated in the field, the DHR isn't just the first shipment. Every OTA update generates a new DHR. You need to record which units received which update, when, and by whom. I've seen auditors ask for the DHR of a specific device that was updated six months ago — if you don't have that, it's a major finding.

**3. Mixing DHF and DMR content.** A common mistake is putting the source code into the DHF. The DHF contains *design outputs* like architecture diagrams and test reports, not the source code itself. The source code is part of the DMR (the recipe). The DHF proves you designed it correctly; the DMR proves you can build it consistently. Keep them separate.

## Try It Yourself

1. **Audit your Git tags.** Go through your last three releases. Do you have a tag that uniquely identifies the exact build environment (compiler version, library versions, OS)? If not, create a DMR tag for your current release and update your CI/CD to enforce this convention.

2. **Map your existing documents to DHF/DMR/DHR.** Take your project's document repository and categorize every file into one of the three buckets. Create a simple index file (like the Markdown example above) that lists each document with its DHF section reference. You'll likely find gaps — missing test reports or design reviews.

3. **Simulate an auditor's trace.** Pick a shipped unit (or a recent release tag). From that DHR, find the exact DMR that was used to build it. From that DMR, find the DHF documents that cover the requirements implemented in that release. Can you trace a single requirement from the SRS through the architecture, detailed design, unit test, integration test, and system test? If not, you have a traceability gap.

## Next Up

Tomorrow is the full review: **Compliance Checklist & Mock Audit**. I'll walk through a complete IEC 62304 audit checklist, simulate an auditor's line of questioning, and show you exactly how to prepare your team for the real thing. Bring your DHF, DMR, and DHR — we're going to find every gap before the auditor does.
