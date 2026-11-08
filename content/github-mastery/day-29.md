---
title: "Day 29: Full Review & Project: Set Up a Medical Firmware Repo with Templates, CI, Projects & Releases"
date: 2026-11-08
tags: ["til", "github-mastery", "review", "project"]
---

# Day 29: Full Review & Project: Set Up a Medical Firmware Repo with Templates, CI, Projects & Releases

## What I Explored Today

Today I consolidated everything from the last four weeks into a single end-to-end exercise: standing up a repository for a hypothetical medical device firmware project (a BLE pulse oximeter) from scratch. The goal wasn't to write firmware — it was to wire up the *repository machinery* that a regulated medical device team actually needs: issue and PR templates that capture traceability, branch protection that enforces review, a CI pipeline that builds and runs static analysis on every push, a Projects board that tracks the design-control workflow, and a release process that produces signed, versioned artifacts with a changelog. This is the "review" day, so I deliberately touched every feature I've covered in the series and verified they compose correctly. Medical firmware raises the stakes on every one of these — a missing review or an untracked change is an audit finding, not just a code smell.

## The Core Concept

The reason to build all of this *before* writing code is that in a regulated context (IEC 62304, FDA design controls), the repository *is* the design history file. Traceability isn't a document you write at the end — it's the link between a requirement (an issue), the change that satisfies it (a PR referencing that issue), the verification that it works (a CI run), and the release that ships it (a tagged release with a changelog). GitHub's primitives map onto that chain almost one-to-one: Issues = requirements/defects, Projects = the workflow state machine, PR templates = the review checklist, branch protection = the approval gate, Actions = automated verification, Releases = controlled distribution. If you set these up deliberately, the audit trail is a *byproduct* of normal engineering work rather than a separate chore. That's the whole point — make compliance fall out of the workflow instead of bolting it on.

## Key Commands / Configuration / Code

**1. Issue template that captures traceability (`.github/ISSUE_TEMPLATE/requirement.yml`):**

```yaml
name: Requirement
description: A traceable software requirement
labels: ["requirement"]
body:
  - type: input
    id: req-id
    attributes:
      label: Requirement ID
      placeholder: "SWR-001"
    validations:
      required: true
  - type: textarea
    id: description
    attributes:
      label: Requirement statement
    validations:
      required: true
  - type: dropdown
    id: risk
    attributes:
      label: Risk classification
      options: ["Class A", "Class B", "Class C"]
    validations:
      required: true
```

**2. PR template with a review checklist (`.github/pull_request_template.md`):**

```markdown
## Change summary
<!-- Link the requirement or defect this addresses -->
Closes #<!-- issue number -->

## Verification
- [ ] Unit tests added/updated
- [ ] Static analysis clean (cppcheck)
- [ ] No new compiler warnings under `-Wall -Wextra -Werror`
- [ ] Reviewed by a second engineer (required for Class B/C)
```

**3. CI workflow — build + static analysis (`.github/workflows/ci.yml`):**

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install toolchain
        run: sudo apt-get update && sudo apt-get install -y cmake gcc-arm-none-eabi cppcheck
      - name: Static analysis
        run: cppcheck --error-exitcode=1 --enable=warning,style src/
      - name: Configure & build
        run: cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build
      - name: Run unit tests
        run: ctest --test-dir build --output-on-failure
```

**4. Branch protection via `gh` CLI (require review + passing CI):**

```bash
gh api -X PUT repos/OWNER/REPO/branches/main/protection \
  -F required_status_checks.strict=true \
  -F 'required_status_checks.contexts[]=build' \
  -F enforce_admins=true \
  -F required_pull_request_reviews.required_approving_review_count=1 \
  -F restrictions=
```

**5. Tagged release with generated notes:**

```bash
git tag -a v1.0.0 -m "First controlled release"
git push origin v1.0.0
gh release create v1.0.0 --generate-notes --title "v1.0.0" build/firmware.elf
```

## Common Pitfalls & Gotchas

- **`--generate-notes` needs PR labels to be useful.** It groups by label, so if your PRs aren't labeled (`bug`, `enhancement`, `requirement`), the changelog is a flat list. Add a labeler workflow or label manually before tagging.
- **Branch protection on `main` blocks your own release commits.** If you protect `main` with `enforce_admins=true`, you can't push tags from a protected branch without a PR — tag from a commit already merged, or use a release branch. Test this before you need it at 5pm on release day.
- **`cppcheck --error-exitcode=1` fails the build on *style* warnings too.** For a medical project you probably want that, but scope `--enable` deliberately — `--enable=all` will flag unused functions in HAL stubs and you'll spend a day suppressing noise. Start with `warning,style` and tighten over time.

## Try It Yourself

1. **Scaffold the repo:** create a new repo, add the three template files above, and open a test issue + PR to confirm the templates render and the checklist appears. Verify the PR body auto-links the issue via `Closes #N`.
2. **Wire up CI and protection:** push the workflow, open a PR that intentionally breaks the build (e.g., add a syntax error), and confirm branch protection blocks the merge until CI is green. Then fix it and merge.
3. **Cut a release:** label a couple of merged PRs, tag `v0.1.0`, and run `gh release create --generate-notes`. Inspect the generated changelog and confirm the build artifact is attached.

## Next up

Tomorrow is the **Full Review** — the capstone of the series. I'll step back from individual features and assess the whole GitHub toolchain: what actually earned its place in a real engineering workflow, what's overkill for small teams, and a decision matrix for which features to adopt at which project stage. If you've been following along, this is the day to consolidate.
