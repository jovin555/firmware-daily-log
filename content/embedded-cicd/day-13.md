---
title: "Day 13: Multi-Target Fan-Out Builds Across Product Variants"
date: 2026-07-13
tags: ["til", "embedded-cicd", "multi-target", "fan-out"]
---

## What I Explored Today

Today I tackled one of the most common scaling problems in embedded CI/CD: how to build firmware for multiple product variants from a single repository without duplicating pipeline logic. Our team supports three hardware revisions (v2, v3, v4) and two regional variants (EU, NA) — that's six distinct firmware images. I implemented a fan-out build pattern using GitLab CI matrix jobs and a unified CMake preset system. The result: one pipeline triggers six parallel builds, each producing a correctly configured binary, with zero manual intervention.

## The Core Concept

Fan-out builds solve a fundamental tension in embedded development: you have one codebase but many targets. The naive approach is a sequential build script that loops over targets — `for target in v2 v3 v4; do make TARGET=$target; done`. This works for a single developer but fails in CI because it serializes builds, wastes runner time, and hides failures (if target v2 fails, you don't know about v3 until you fix v2).

The correct pattern is **fan-out**: one pipeline stage fans out into N parallel jobs, each building a specific target variant. Each job is isolated, runs its own compilation, and reports success/failure independently. This gives you:
- **Parallel execution** — all variants build simultaneously
- **Independent failure reporting** — know exactly which variant broke
- **Artifact isolation** — each variant's binary is tagged and stored separately
- **Scalable resource usage** — add more runners, add more variants

The key enabler is a **build matrix** (GitLab CI `parallel:matrix`, GitHub Actions `strategy:matrix`, Jenkins `matrix`). Combined with a **toolchain abstraction layer** (CMake presets, Kconfig, or environment variables), you define the variants once and let the CI engine handle the rest.

## Key Commands / Configuration / Code

### 1. CMake Presets for Variant Configuration

First, define each variant's toolchain and flags in `CMakePresets.json`. This keeps the build logic in the repo, not the CI config.

```json
{
  "version": 6,
  "configurePresets": [
    {
      "name": "v2-eu",
      "displayName": "Hardware v2, EU region",
      "binaryDir": "build/v2-eu",
      "cacheVariables": {
        "TARGET_HW_REV": "v2",
        "TARGET_REGION": "EU",
        "TOOLCHAIN_FILE": "cmake/toolchain-arm-gcc.cmake"
      }
    },
    {
      "name": "v3-na",
      "displayName": "Hardware v3, NA region",
      "binaryDir": "build/v3-na",
      "cacheVariables": {
        "TARGET_HW_REV": "v3",
        "TARGET_REGION": "NA",
        "TOOLCHAIN_FILE": "cmake/toolchain-arm-gcc.cmake"
      }
    }
    // ... remaining 4 variants
  ]
}
```

### 2. GitLab CI Matrix Job

The `.gitlab-ci.yml` uses `parallel:matrix` to fan out. Each job gets unique variables from the matrix.

```yaml
stages:
  - build

variables:
  GIT_SUBMODULE_STRATEGY: recursive

build-variants:
  stage: build
  parallel:
    matrix:
      - HW_REV: ["v2", "v3", "v4"]
        REGION: ["EU", "NA"]
  script:
    # Configure using the preset named "{HW_REV}-{REGION}"
    - cmake --preset ${HW_REV}-${REGION}
    # Build the configured variant
    - cmake --build build/${HW_REV}-${REGION} --target firmware.hex
  artifacts:
    paths:
      # Store only the hex file, tagged with variant name
      - build/${HW_REV}-${REGION}/firmware.hex
    name: "firmware-${HW_REV}-${REGION}"
    expire_in: 1 week
```

This generates 6 parallel jobs (`v2-EU`, `v2-NA`, `v3-EU`, `v3-NA`, `v4-EU`, `v4-NA`). Each job:
- Checks out the same commit
- Runs `cmake --preset` with its specific variables
- Builds only its target
- Exports the hex as a uniquely named artifact

### 3. Conditional Compilation in Source

Inside the firmware, use the CMake-defined variables to select code paths.

```c
// main.c
#if TARGET_HW_REV == 2
    #include "gpio_v2.h"
    #define LED_PIN 13
#elif TARGET_HW_REV == 3
    #include "gpio_v3.h"
    #define LED_PIN 14
#endif

#if TARGET_REGION == EU
    #define RADIO_FREQ_MHZ 868
#elif TARGET_REGION == NA
    #define RADIO_FREQ_MHZ 915
#endif
```

## Common Pitfalls & Gotchas

### 1. Shared Build Cache Poisoning
When fanning out, each job must have its own build directory. If two jobs share the same `build/` directory (e.g., because you forgot the `--preset` and used a default), they'll clobber each other's object files. Always use `binaryDir` in presets or `-B` in CMake to enforce isolation. I've seen a v2 binary silently include v3's linker script because of this — the build succeeded but the firmware bricked hardware.

### 2. Matrix Explosion
Six variants is manageable. But if you add features (BLE vs no-BLE, battery vs wired, debug vs release), the matrix grows multiplicatively. 3 HW revs × 2 regions × 2 features = 12 jobs. This can exhaust runner capacity or hit CI platform limits (GitLab free tier caps at 400 jobs/month). Mitigate by:
- Building only the "release" configuration in CI; debug builds on demand
- Using a two-stage fan-out: first build the base, then apply feature flags in a second matrix
- Capping matrix size with `parallel:matrix:max-parallel` (GitLab) or `max-parallel` (GitHub)

### 3. Artifact Name Collisions
Without unique artifact names, the last job to finish overwrites the previous one. Always include variant identifiers in the artifact `name` field. I use `firmware-${HW_REV}-${REGION}.hex`. Also set `expire_in` — embedded hex files are small, but 6 jobs × 10 builds/day × 30 days = 1800 artifacts.

## Try It Yourself

1. **Add a new variant to your existing CMake project.** Create a new preset in `CMakePresets.json` that changes a preprocessor define (e.g., `LED_BLINK_RATE_MS`). Run `cmake --preset my-variant && cmake --build build/my-variant` to verify it compiles differently.

2. **Convert a sequential build script to a matrix job.** If you have a shell script that loops over targets (`for t in a b c; do make TARGET=$t; done`), rewrite it as a GitLab CI `parallel:matrix` or GitHub Actions `strategy:matrix`. Run it and confirm all variants build in parallel.

3. **Set up artifact tagging.** Modify your CI config so each variant's binary is stored with a unique name containing the variant identifier. Download two artifacts and verify they have different checksums (they should, if the variants differ).

## Next Up

Tomorrow: **Deployment Gates: Manual Approval Before Field Rollout**. We'll explore how to add a human-in-the-loop step before firmware reaches production devices — using protected environments, approval workflows, and signed release candidates.
