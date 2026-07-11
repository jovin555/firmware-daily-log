---
title: "Day 11: Binary Size Regression Tracking Across Builds"
date: 2026-07-11
tags: ["til", "embedded-cicd", "binary-size", "regression"]
---

## What I Explored Today

Today I tackled a problem that haunts every embedded team: binary size regressions sneaking into production. I set up automated size tracking across our CI pipeline using `size` output from the GNU toolchain, `awk` for parsing, and a lightweight JSON history file stored as a CI artifact. The goal: catch a 512-byte bloat before it compounds across a million-unit shipment.

## The Core Concept

In embedded systems, every byte matters. A 2KB regression in firmware might mean a field-upgrade failure, a violated bootloader partition boundary, or a product that no longer fits in its allocated flash sector. Manual review of `arm-none-eabi-size` output is error-prone and doesn't scale across dozens of commits per day.

Binary size regression tracking works by:
1. Extracting the `.text`, `.data`, and `.bss` section sizes from the linker output after each build.
2. Comparing these values against a stored baseline (usually the last known-good build or a specific release tag).
3. Failing the pipeline if the delta exceeds a configurable threshold (e.g., +1% or +256 bytes).

The key insight: you don't need a fancy SaaS tool. A Makefile target, a Python script, or even a shell pipeline can do this reliably. The hard part is deciding *what* to compare against and *when* to update the baseline. I settled on a strategy where the baseline is the last commit on the `main` branch, stored as a JSON file committed to the repo. Each PR build compares against that baseline, and merges update the baseline.

## Key Commands / Configuration / Code

Here's the core pipeline step I implemented today. It runs after a successful build and before any deployment.

```bash
#!/bin/bash
# track_size.sh - Run after firmware build
# Expects: firmware.elf in $BUILD_DIR

BUILD_DIR="build"
ELF="${BUILD_DIR}/firmware.elf"
BASELINE_FILE=".size-baseline.json"
THRESHOLD_BYTES=512  # Fail if any section grows by more than this

# Step 1: Extract sizes using arm-none-eabi-size in SVR4 format
# Output: text    data     bss     dec     hex filename
#         1234     56      78    1368     558 firmware.elf
SIZE_OUTPUT=$(arm-none-eabi-size -A "$ELF" | tail -n +2 | awk '{print $1, $2}')

# Step 2: Parse into structured JSON (using jq if available, else manual)
TEXT=$(echo "$SIZE_OUTPUT" | grep "^\.text" | awk '{print $2}')
DATA=$(echo "$SIZE_OUTPUT" | grep "^\.data" | awk '{print $2}')
BSS=$(echo "$SIZE_OUTPUT" | grep "^\.bss" | awk '{print $2}')

# Step 3: Compare against baseline
if [ -f "$BASELINE_FILE" ]; then
    BASELINE_TEXT=$(jq -r '.text' "$BASELINE_FILE")
    BASELINE_DATA=$(jq -r '.data' "$BASELINE_FILE")
    BASELINE_BSS=$(jq -r '.bss' "$BASELINE_FILE")
    
    DELTA_TEXT=$((TEXT - BASELINE_TEXT))
    DELTA_DATA=$((DATA - BASELINE_DATA))
    DELTA_BSS=$((BSS - BASELINE_BSS))
    
    # Check each section
    for DELTA in "$DELTA_TEXT" "$DELTA_DATA" "$DELTA_BSS"; do
        if [ "$DELTA" -gt "$THRESHOLD_BYTES" ]; then
            echo "FAIL: Size regression of ${DELTA} bytes (threshold: ${THRESHOLD_BYTES})"
            exit 1
        fi
    done
    echo "PASS: All sections within threshold"
else
    echo "No baseline found. Creating baseline from this build."
    # Write baseline for future comparisons
    jq -n --argjson text "$TEXT" --argjson data "$DATA" --argjson bss "$BSS" \
        '{text: $text, data: $data, bss: $bss}' > "$BASELINE_FILE"
fi
```

For the CI pipeline (GitHub Actions example):

```yaml
# .github/workflows/size-check.yml
jobs:
  build-and-check-size:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Needed to get baseline from main
      - name: Build firmware
        run: make
      - name: Check binary size
        run: bash track_size.sh
      - name: Upload size report
        uses: actions/upload-artifact@v4
        with:
          name: size-report
          path: .size-baseline.json
```

## Common Pitfalls & Gotchas

1. **Linker garbage collection changes section sizes.** If you enable `-ffunction-sections -fdata-sections -Wl,--gc-sections`, the `.text` and `.data` sections will shrink as unused code is removed. Your baseline will be stale the moment you toggle these flags. Always regenerate the baseline after any linker script or optimization flag change.

2. **Debug symbols inflate ELF size but not flash usage.** The `arm-none-eabi-size` output on an ELF includes debug sections (`.debug_*`). Use `arm-none-eabi-size -A` and filter to only `.text`, `.data`, and `.bss` — or better, use `arm-none-eabi-objcopy -O binary firmware.elf firmware.bin` and check the binary file size directly.

3. **Thresholds must account for normal variation.** A single new feature might legitimately add 2KB. Set your threshold to something reasonable (e.g., 1% of total flash or 512 bytes) and document exceptions in commit messages. I've seen teams set thresholds to 0 bytes and then spend hours triaging every merge.

## Try It Yourself

1. **Add a size-check target to your Makefile.** Create a target `size-check` that runs `arm-none-eabi-size` on your firmware ELF and compares it to a stored baseline. Fail the build if `.text` grows by more than 256 bytes.

2. **Generate a size trend graph.** Modify the tracking script to append each build's size to a CSV file (commit_hash, text, data, bss, timestamp). Use a simple Python script with `matplotlib` to plot the trend over the last 100 commits.

3. **Set up a baseline update on merge.** In your CI, configure a workflow that runs only on pushes to `main`. After a successful build, it should update the `.size-baseline.json` file and commit it back to the repo (using a bot account or PAT).

## Next Up

Tomorrow, I'm diving into **SBOM Generation & Dependency CVE Scanning in the Pipeline**. We'll generate a Software Bill of Materials from our Zephyr/FreeRTOS dependencies, scan it against the NVD database, and fail the build if a critical CVE is found in a linked library. No more shipping firmware with known vulnerabilities.
