---
title: "Day 12: SBOM Generation & Dependency CVE Scanning in the Pipeline"
date: 2026-07-12
tags: ["til", "embedded-cicd", "sbom", "cve-scanning"]
---

## What I Explored Today

Today I integrated Software Bill of Materials (SBOM) generation and automated CVE scanning into our embedded CI/CD pipeline. After shipping a firmware update last quarter that unknowingly included a vulnerable version of `mbedtls` (CVE-2023-43615, a buffer overflow in the TLS handshake), the security team mandated that every build must produce a verifiable SBOM and pass dependency vulnerability checks before deployment. I spent the day wiring up `syft` for SBOM generation, `grype` for CVE scanning, and enforcing a fail-fast policy in GitLab CI when critical vulnerabilities are detected in our Zephyr RTOS and FreeRTOS builds.

## The Core Concept

An SBOM is a machine-readable inventory of every component in your firmware—libraries, toolchain versions, OS kernel patches, and even compiler flags. For embedded systems, this is critical because:

1. **Supply chain attacks** are rising—the 2024 xz utils backdoor showed that a single compromised dependency can cascade into millions of devices.
2. **Regulatory compliance** (e.g., US Executive Order 14028, EU Cyber Resilience Act) now mandates SBOMs for medical, automotive, and IoT devices.
3. **Vulnerability remediation** requires knowing exactly which version of `FreeRTOS+TCP` or `LwIP` you shipped to a field-deployed device.

The pipeline pattern is: **build → generate SBOM → scan SBOM for CVEs → gate on severity**. If a critical CVE exists in a production dependency, the pipeline fails before the artifact is published.

## Key Commands / Configuration / Code

### 1. SBOM Generation with Syft (in CI)

We use Anchore’s `syft` because it supports embedded toolchains and can catalog statically linked binaries, not just package managers.

```yaml
# .gitlab-ci.yml snippet
sbom-generation:
  stage: static-analysis
  image: anchore/syft:latest
  script:
    # Generate SPDX 2.3 SBOM from the build artifact directory
    - syft dir:build/ --output spdx-json=build.sbom.spdx.json
    # Also generate CycloneDX for tools that prefer it
    - syft dir:build/ --output cyclonedx-json=build.sbom.cyclonedx.json
  artifacts:
    paths:
      - build.sbom.spdx.json
      - build.sbom.cyclonedx.json
    expire_in: 30 days
```

For Zephyr builds, we also catalog the Zephyr SDK and toolchain:

```bash
# In the build script, before syft runs
# Catalog the Zephyr SDK (installed at /opt/zephyr-sdk)
syft dir:/opt/zephyr-sdk --output spdx-json=zephyr-sdk.sbom.json
```

### 2. CVE Scanning with Grype

Grype reads the SBOM and cross-references CVEs from the National Vulnerability Database (NVD) and GitHub Advisory Database.

```yaml
cve-scan:
  stage: static-analysis
  image: anchore/grype:latest
  needs: ["sbom-generation"]
  script:
    # Scan the SPDX SBOM directly
    - grype sbom:build.sbom.spdx.json --fail-on critical --output table
    # Also scan the filesystem for any missed dependencies
    - grype dir:build/ --fail-on critical --output json > cve-report.json
  artifacts:
    paths:
      - cve-report.json
    when: always  # Capture even on failure for debugging
```

### 3. Failing on Critical CVEs with Policy

We enforce a policy that blocks the pipeline on critical or high CVEs, but allows medium/low with a warning:

```yaml
# In the same job, or a separate policy-check job
- grype sbom:build.sbom.spdx.json --fail-on high --only-fixed
```

The `--only-fixed` flag is crucial—it ignores CVEs that have no fix available yet, preventing false positives that block shipping.

### 4. Integrating with Zephyr’s West Build System

For Zephyr projects, dependencies come from the manifest (`west.yml`). We generate an SBOM from the manifest before the build:

```bash
# Extract all git SHAs from west.yml and feed to syft
west list --format="{path} {revision}" | while read repo sha; do
  syft dir:$repo --source-version $sha --output spdx-json >> combined.sbom.json
done
```

## Common Pitfalls & Gotchas

### 1. **False Positives from Static Linking**
Embedded firmware statically links everything. Grype may flag a CVE in `libc` that exists in the toolchain’s `newlib` but is not actually compiled into your binary. **Mitigation**: Use `--only-fixed` and maintain a CVE allowlist (`grype --exclude` for known false positives).

### 2. **SBOM Size Bloat**
A Zephyr build with 50+ modules can produce a 10MB+ SBOM. This slows down artifact uploads and parsing. **Mitigation**: Compress SBOMs (`gzip build.sbom.spdx.json`) and set aggressive artifact expiration (7–30 days).

### 3. **Toolchain Dependencies Not Cataloged**
Syft by default scans package managers (apt, pip, npm) but may miss the ARM GCC toolchain or Zephyr SDK installed outside standard paths. **Mitigation**: Explicitly run `syft dir:` on the toolchain installation directory and merge SBOMs with `syft packages --catalogers all`.

## Try It Yourself

1. **Generate an SBOM for your current firmware build**: Run `syft dir:build/ --output spdx-json` on your latest build artifact. Examine the output—does it list every library you expect? If not, add explicit `syft dir:` calls for toolchain directories.

2. **Scan for CVEs and gate your pipeline**: Add a Grype scan step that fails on `--fail-on high`. Run it against your SBOM. How many critical CVEs appear? If more than 3, investigate whether they are real or false positives.

3. **Automate SBOM generation from your build system**: If you use Zephyr, write a script that parses `west.yml` and generates a combined SBOM from all manifest modules. If you use CMake, hook `syft` into a post-build step using `add_custom_command`.

## Next Up

Tomorrow, we tackle **Multi-Target Fan-Out Builds Across Product Variants**—how to compile firmware for 12 different MCU targets (STM32, nRF, ESP32, etc.) in parallel, reuse build artifacts, and avoid 3-hour CI pipelines. We’ll cover matrix strategies, caching, and conditional compilation in GitLab CI and GitHub Actions.
