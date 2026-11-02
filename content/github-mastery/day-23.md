---
title: "Day 23: Security Advisories, SECURITY.md, SBOMs & Artifact Attestations"
date: 2026-11-02
tags: ["til", "github-mastery", "supply-chain", "sbom"]
---

# Day 23: Security Advisories, SECURITY.md, SBOMs & Artifact Attestations

## What I Explored Today

Today I went deep on the supply-chain security surface that GitHub exposes beyond Dependabot alerts. That means four distinct but related things: private vulnerability reporting via GitHub Security Advisories (GHSA), the `SECURITY.md` file that tells researchers *how* to reach you, Software Bill of Materials (SBOM) generation and export, and artifact attestations — the newer `actions/attest-build-provenance` mechanism that cryptographically binds a build artifact to the workflow that produced it. I spent most of the day on attestations because that's where the tooling has moved fastest, and because it's the piece that actually lets a downstream consumer verify *provenance*, not just scan for known CVEs.

## The Core Concept

Most teams treat "security" as a scanner problem: run CodeQL, run Dependabot, done. But scanners answer "is there a known bad thing in my dependency tree?" They don't answer three questions that matter just as much:

1. **How does someone report a vulnerability to me privately?** If there's no `SECURITY.md` and no private reporting enabled, researchers either open a public issue (disclosing the bug to the world) or give up. GHSA gives you a private fork, a draft advisory, a CVE request path, and coordinated disclosure — all inside the repo.
2. **What exactly is in the thing I shipped?** An SBOM is a machine-readable inventory (SPDX or CycloneDX) of every component and version in a build. When the next Log4Shell lands, an SBOM is the difference between "we think we're affected" and a `grep`.
3. **Did the artifact I'm about to deploy actually come from this repo's CI, or did someone rebuild it locally and swap it?** That's provenance, and that's what attestations solve. Sigstore-backed attestations let a consumer run `gh attestation verify` and get a cryptographic yes/no.

The mental model: advisories are the *inbound* channel, `SECURITY.md` is the *signpost*, SBOM is the *inventory*, and attestations are the *chain of custody*. They're complementary, not redundant.

## Key Commands / Configuration / Code

**1. `SECURITY.md`** — put it in the repo root, `.github/`, or `docs/`. GitHub surfaces it under the Security tab automatically.

```markdown
# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 2.x     | :white_check_mark: |
| 1.x     | :x:                |

## Reporting a Vulnerability

Please use GitHub's private vulnerability reporting
(Security tab → "Report a vulnerability"). Do **not** open a public issue.
We aim to acknowledge within 3 business days.
```

Enable private reporting via the API (the UI toggle lives under Settings → Code security):

```bash
# Requires admin on the repo; scope: repo
gh api -X PUT repos/OWNER/REPO/private-vulnerability-reporting
```

**2. Draft a security advisory from the CLI:**

```bash
# Create a draft advisory (returns a GHSA id you can publish later)
gh api repos/OWNER/REPO/security-advisories \
  -f summary="Heap overflow in parser" \
  -f description="Crafted input can overflow the buffer in parse()." \
  -f severity="high" \
  -f "vulnerabilities[][package][ecosystem]=npm" \
  -f "vulnerabilities[][package][name]=my-pkg" \
  -f "vulnerabilities[][vulnerable_version_range]=< 2.1.3" \
  -f "vulnerabilities[][patched_versions]=2.1.3"
```

**3. Generate an SBOM.** GitHub can export one from the dependency graph, but in CI you usually want it as a build artifact:

```yaml
# .github/workflows/sbom.yml
name: SBOM
on: [push]
permissions:
  contents: write
jobs:
  sbom:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Generate SPDX SBOM
        uses: anchore/sbom-action@v0
        with:
          format: spdx-json
          output-file: sbom.spdx.json
      - uses: actions/upload-artifact@v4
        with:
          name: sbom
          path: sbom.spdx.json
```

**4. Artifact attestations.** This is the important one. Build provenance requires `id-token: write` and `attestations: write`:

```yaml
name: Release
on:
  push:
    tags: ['v*']
permissions:
  contents: read
  id-token: write        # required for Sigstore OIDC signing
  attestations: write    # required to persist the attestation
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: ./build.sh && sha256sum dist/*.tar.gz > checksums.txt
      - uses: actions/attest-build-provenance@v1
        with:
          subject-path: 'dist/*.tar.gz'
```

Then a consumer verifies it:

```bash
# Fails if the artifact wasn't produced by the expected workflow in the expected repo
gh attestation verify dist/myapp-1.2.3.tar.gz --repo OWNER/REPO
```

The verification checks the Sigstore bundle against the repo's OIDC identity and the workflow ref — so a locally rebuilt tarball with the same bytes but no attestation will fail.

## Common Pitfalls & Gotchas

- **Attestations need the right permissions, and the failure mode is silent-ish.** If you forget `id-token: write`, the action errors at signing time; if you forget `attestations: write`, the bundle can't be persisted. Both are easy to miss because the build step itself succeeds. Also note attestations are only available on public repos (and private repos on GitHub Enterprise Cloud) — check your plan before wiring this into a release pipeline.
- **SBOMs go stale the moment you generate them.** An SBOM reflects the dependency tree *at build time*. If you generate it on every push but never attach it to the release, you have a pile of artifacts nobody queries. Attach the SBOM to the GitHub Release alongside the binaries so consumers can correlate a shipped version with its inventory.
- **A published advisory is not the same as a CVE.** GHSA assigns its own `GHSA-xxxx` identifier and *can* request a CVE, but only if the repo is in a CNA-covered ecosystem or you go through GitHub as a CNA. Don't promise researchers a CVE in your `SECURITY.md` unless you've confirmed the path — and remember that once an advisory is published, the private fork and its commits become visible.

## Try It Yourself

1. **Add `SECURITY.md` and enable private reporting** on one of your repos. Then use `gh api repos/OWNER/REPO/security-advisories` to open a *draft* advisory against a fake package and confirm it appears under the Security tab without being public.
2. **Wire up SBOM generation** in a workflow using `anchore/sbom-action`, upload the SPDX file as an artifact, and inspect it — grep for a transitive dependency you didn't know you had.
3. **Attest and verify.** Add `actions/attest-build-provenance@v1` to a release workflow, push a tag, then run `gh attestation verify <artifact> --repo OWNER/REPO`. Then deliberately tamper with the artifact (append a byte) and confirm verification fails.

## Next up

Tomorrow: **Discussions, Wikis & Community Health Files** — turning a repo from a code dump into a project people can actually participate in. We'll cover enabling Discussions, converting issues to discussions, the `CONTRIBUTING.md` / `CODE_OF_CONDUCT.md` / issue-template triad, and when a Wiki is the right call versus just using `docs/`.
