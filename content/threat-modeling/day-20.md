---
title: "Day 20: Supply Chain Threats: Third-Party Libraries & SBOM"
date: 2026-07-20
tags: ["til", "threat-modeling", "supply-chain", "sbom"]
---

## What I Explored Today

Today I dug into the supply chain attack surface that every embedded system inherits the moment we `git clone` a third-party library or `apt install` a toolchain package. The Log4j vulnerability (CVE-2021-44228) was a wake-up call, but for embedded engineers, the real nightmare is a backdoored BSP (Board Support Package) or a compromised RTOS distribution. I focused on how to produce and consume Software Bill of Materials (SBOMs) in the SPDX 2.3 format, and how to integrate SBOM validation into a CI pipeline using `syft` and `grype` — tools that actually work on embedded targets.

## The Core Concept

A supply chain threat isn't just "someone might hack our vendor." It's that every transitive dependency — every header file, every static library archive, every precompiled blob — is an unverified trust boundary. In embedded systems, we often vendor third-party code directly into our firmware images. Once that binary is linked, you cannot patch it over the air without a full OTA update. The SBOM is your inventory manifest: it lists every component, version, license, and known vulnerability. Without it, you're flying blind when the next CVE drops.

The key insight: SBOMs must be *generated at build time*, not post-hoc. If you generate an SBOM from a binary, you lose dependency relationships. If you generate it from source, you capture the exact graph of what went into the image. For embedded work, that means hooking into your CMake or Make build system to emit SPDX JSON at link time.

## Key Commands / Configuration / Code

### 1. Generating an SBOM for a firmware project with `syft`

```bash
# Install syft (works on Linux, macOS, Windows)
curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh | sh -s -- -b /usr/local/bin

# Generate SPDX 2.3 SBOM from a build directory containing .elf, .a, .o files
# syft scans directories for known package types (Cargo.toml, conanfile.txt, etc.)
syft dir:./build/ --output spdx-json=./firmware_sbom.spdx.json

# For a containerized toolchain (e.g., ARM GCC in Docker)
syft docker:arm-gcc:latest --output spdx-json=toolchain_sbom.spdx.json
```

### 2. Scanning an SBOM for known vulnerabilities with `grype`

```bash
# Install grype
curl -sSfL https://raw.githubusercontent.com/anchore/grype/main/install.sh | sh -s -- -b /usr/local/bin

# Scan the SBOM we just generated
grype sbom:./firmware_sbom.spdx.json --output table

# Example output (abbreviated):
# NAME          INSTALLED  FIXED-IN  TYPE       VULNERABILITY
# libcurl.so.4  7.79.1     7.80.0    deb        CVE-2021-22946
# zlib          1.2.11     1.2.12    archive    CVE-2022-37434
```

### 3. CI pipeline integration (GitHub Actions snippet)

```yaml
# .github/workflows/sbom-check.yml
name: SBOM Generation & Vulnerability Scan
on: [push, pull_request]

jobs:
  sbom:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build firmware
        run: |
          cmake -B build -DCMAKE_TOOLCHAIN_FILE=arm-gcc-toolchain.cmake
          cmake --build build
      - name: Generate SBOM
        uses: anchore/syft-action@v0.17.0
        with:
          path: ./build/
          output-format: spdx-json
          output-file: firmware_sbom.spdx.json
      - name: Scan SBOM for vulnerabilities
        uses: anchore/grype-action@v0.17.0
        with:
          sbom: firmware_sbom.spdx.json
          fail-build: true  # Fail if any critical vulnerability found
      - name: Archive SBOM
        uses: actions/upload-artifact@v4
        with:
          name: sbom
          path: firmware_sbom.spdx.json
```

### 4. Verifying SBOM integrity (hash pinning)

```bash
# Generate SHA-256 hash of the SBOM and sign it
sha256sum firmware_sbom.spdx.json > firmware_sbom.spdx.json.sha256

# Later, verify the SBOM hasn't been tampered with
sha256sum -c firmware_sbom.spdx.json.sha256
```

## Common Pitfalls & Gotchas

1. **Static linking hides dependencies.** If you statically link `libcrypto.a`, `syft` may not detect OpenSSL unless you explicitly tell it to scan `.a` files. Always run `syft` on the *build directory* containing intermediate objects, not just the final `.elf`. Use `--exclude` to skip generated headers.

2. **SBOMs expire.** A clean scan today means nothing tomorrow. New CVEs are published daily. You must re-scan your SBOMs on a schedule (e.g., weekly cron job) and alert on new findings. Tools like `grype` can use `--only-fixed` to ignore unfixed vulnerabilities.

3. **Toolchain SBOMs are often ignored.** Your compiler, linker, and assembler are also third-party software. A backdoored GCC could inject malicious code into every firmware build. Generate an SBOM for your toolchain container and scan it separately. Use `syft docker:` to capture the full OS package list.

## Try It Yourself

1. **Generate an SBOM for your current project.** Run `syft dir:./build/ --output spdx-json=my_project.spdx.json`. If you don't have a build directory, create a dummy one with a few `.a` files and a `conanfile.txt`. Inspect the JSON — look for the `packages` array and `relationships` field.

2. **Scan the SBOM for vulnerabilities.** Run `grype sbom:my_project.spdx.json --output table`. Identify one vulnerability and check if a fixed version exists. If you don't have real CVEs, use `--only-fixed` to see only vulnerabilities with patches.

3. **Add SBOM generation to your CI pipeline.** Use the GitHub Actions snippet above (or adapt for GitLab CI/Jenkins). Ensure the build fails if a critical CVE is found. Archive the SBOM as a build artifact.

## Next Up

Tomorrow: **IEC 62443: Industrial Cybersecurity Threat Modeling** — we'll map STRIDE to the Purdue Model levels and walk through a threat model for a PLC firmware update process. Bring your ICS/SCADA hat.
