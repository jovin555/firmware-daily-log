---
title: "Day 07: Software Configuration Management Plan"
date: 2026-06-19
tags: ["til", "iec62304", "scm", "versioning"]
---

## What I Explored Today

Today I dug into the Software Configuration Management (SCM) Plan as required by IEC 62304 Clause 5.2. The standard mandates that every medical device software project must have a documented SCM plan before any development work begins. I spent the afternoon mapping out how to structure this plan for a real embedded system—an infusion pump controller running FreeRTOS on an STM32. The key insight: SCM isn't just about Git branches; it's about establishing a repeatable, auditable process for identifying, controlling, and tracking every software item throughout the product lifecycle.

## The Core Concept

The SCM plan answers one fundamental question: *How do we know exactly what software was in the device at any point in time?* For a Class B or C device, the regulatory burden is high. If a field failure occurs, you must be able to reproduce the exact binary, with all its dependencies, that shipped six months ago. The SCM plan defines the rules for:

- **Configuration identification** — every source file, library, toolchain, and build script gets a unique identifier.
- **Change control** — no one modifies a baseline without a documented review and approval.
- **Configuration status accounting** — you can query the current state of any configuration item at any time.
- **Configuration audits** — periodic checks that the physical configuration matches the documented one.

The plan itself is a living document. It lives in your repository (not a shared drive) and evolves as your toolchain or compliance requirements change. The standard doesn't prescribe a specific tool—Git, SVN, or even a well-maintained file server can work—but it does require that the plan be *enforced*, not just written.

## Key Commands / Configuration / Code

Here's the SCM plan structure I'm using, with real Git commands that enforce the policy:

```yaml
# scm-plan.yaml — Software Configuration Management Plan
# IEC 62304 Clause 5.2 compliant

version: "1.0"
effective_date: "2026-06-19"

# 1. Configuration Items
# Every item gets a unique ID: <component>-<version>
items:
  - id: "firmware-core-v3.2.1"
    path: "src/firmware/"
    type: "source"
    hash: "sha256: a1b2c3d4..."
  - id: "rtos-kernel-v10.4.3"
    path: "lib/FreeRTOS/"
    type: "third-party"
    hash: "sha256: e5f6g7h8..."
  - id: "toolchain-gcc-arm-v12.2"
    path: "toolchain/"
    type: "tool"
    version_cmd: "arm-none-eabi-gcc --version"

# 2. Branching Strategy
# main = released, validated builds only
# develop = integration testing
# feature/<ticket-id> = individual work
# release/<version> = release candidates
branching:
  main:
    protection: "requires 2 approvals"
    require_ci: true
  develop:
    protection: "requires 1 approval"
    require_ci: true

# 3. Baseline Procedure
# On every release, create a signed tag
baseline:
  command: |
    git tag -s v$(VERSION) -m "Release $(VERSION)"
    git archive --format=zip -o release-$(VERSION).zip HEAD
  verification: |
    sha256sum release-$(VERSION).zip > checksum.txt
    gpg --verify v$(VERSION).tar.gz.asc

# 4. Change Control
# Every change must reference a ticket
commit_template: |
  <type>(<scope>): <description>
  Ticket: <JIRA-ID>
  Risk: <Low|Medium|High>
  Reviewed-by: <name>
```

The actual Git hooks that enforce this:

```bash
#!/bin/bash
# .git/hooks/commit-msg — Enforce commit message format
# IEC 62304 Clause 5.2.3 — Change control

COMMIT_MSG_FILE=$1
COMMIT_MSG=$(cat "$COMMIT_MSG_FILE")

# Check for ticket reference
if ! echo "$COMMIT_MSG" | grep -qE "^Ticket: [A-Z]+-[0-9]+"; then
    echo "ERROR: Commit must include a ticket reference (e.g., Ticket: PROJ-123)"
    exit 1
fi

# Check for risk assessment
if ! echo "$COMMIT_MSG" | grep -qE "^Risk: (Low|Medium|High)"; then
    echo "ERROR: Commit must include risk assessment (Risk: Low|Medium|High)"
    exit 1
fi

# Check for reviewer
if ! echo "$COMMIT_MSG" | grep -qE "^Reviewed-by:"; then
    echo "ERROR: Commit must include reviewer (Reviewed-by: name)"
    exit 1
fi

exit 0
```

## Common Pitfalls & Gotchas

**1. Forgetting third-party dependencies in the baseline.** Your SCM plan must include every library and tool. I've seen teams meticulously version their own code but pull in a FreeRTOS kernel from a GitHub URL without pinning the commit hash. When the vendor updates their repo, your build silently changes. Always vendor third-party code into your repository or use a lockfile (e.g., `git submodule` with a pinned commit, or a `conanfile.lock`).

**2. Treating the SCM plan as a one-time document.** The plan must be updated when your process changes. If you switch from Jenkins to GitHub Actions, update the plan. If you add a new static analysis tool, update the plan. The auditor will check that your actual workflow matches the documented plan. A stale plan is worse than no plan—it shows you aren't following your own process.

**3. Not testing the restore procedure.** The whole point of SCM is reproducibility. I've watched teams confidently tag a release, then discover their backup server failed six months later. Test your restore process quarterly: clone the repo from scratch, run the build, and verify the binary hash matches the release notes. If you can't reproduce a build from a tag, your SCM plan has failed.

## Try It Yourself

1. **Create a commit-msg hook** that enforces a ticket reference and risk assessment. Apply it to a test repository and verify it rejects non-compliant commits. Then, write a second hook that prevents direct pushes to `main` (use `pre-receive` on the server side).

2. **Document your current SCM process** in a YAML file similar to the example above. Include every configuration item: source code, toolchain, build scripts, test fixtures, and documentation. For each item, record its version or hash and where it's stored.

3. **Perform a baseline restore test.** Pick a release tag from six months ago (or create one if you don't have one). Clone the repository, checkout the tag, and attempt a full build. Compare the output binary's SHA256 hash to the one recorded in the release notes. Document any discrepancies.

## Next Up

Tomorrow: **Traceability Matrix: Requirements to Design to Test** — how to build a bidirectional mapping that proves every requirement has a design element and a test case, and how to automate the matrix updates so it doesn't become a documentation nightmare.
