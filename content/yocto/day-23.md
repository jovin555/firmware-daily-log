---
title: "Day 23: Reproducible Builds & SOURCE_DATE_EPOCH"
date: 2026-07-05
tags: ["til", "yocto", "reproducible-builds"]
---

## What I Explored Today

Today I dove into reproducible builds in Yocto, specifically how `SOURCE_DATE_EPOCH` eliminates build-time variance. When you build the same source twice, you should get byte-identical output—but timestamps, build paths, and host-specific data break that. I configured a Poky-based build to produce deterministic images and verified the results with `diffoscope`. The goal: trust that a production image matches exactly what was tested, without rebuilding from the same commit producing a different hash.

## The Core Concept

Reproducible builds matter for security and production compliance. If you can't prove that your deployed image matches your source, you can't detect tampering or verify supply chain integrity. In Yocto, the biggest culprit is timestamps embedded during compilation—every `__DATE__`, `__TIME__`, or file modification time changes between builds.

`SOURCE_DATE_EPOCH` is the solution. It's a Unix timestamp (seconds since 1970-01-01) that tools like `gcc`, `binutils`, and `cpio` read to override the current time. When set, every build artifact uses that fixed timestamp instead of `now`. The result: two builds from identical source produce identical binaries.

Yocto's `reproducible_build.bbclass` handles this automatically when enabled. It sets `SOURCE_DATE_EPOCH` to the latest source file timestamp in the recipe's `S` directory, or falls back to the recipe's `PV` (version) timestamp. For full control, you override it globally.

## Key Commands / Configuration / Code

### 1. Enable reproducible builds globally

In `local.conf`:

```bitbake
# Enable the reproducible build class for all recipes
INHERIT += "reproducible_build"

# Optionally force a fixed epoch (e.g., for a release)
# SOURCE_DATE_EPOCH = "1719878400"  # 2024-07-01 00:00:00 UTC
```

Without `INHERIT`, only recipes that explicitly inherit the class get deterministic timestamps.

### 2. Verify a recipe's SOURCE_DATE_EPOCH

```bash
# Check what timestamp a recipe uses
bitbake -e core-image-minimal | grep ^SOURCE_DATE_EPOCH=

# Output example:
# SOURCE_DATE_EPOCH="1719878400"
```

If it's empty, the recipe isn't using the class, or the fallback failed.

### 3. Build and compare two images

```bash
# First build
bitbake core-image-minimal
cp tmp/deploy/images/qemux86-64/core-image-minimal-qemux86-64.wic build1.wic

# Clean only the output, not sstate
bitbake core-image-minimal -c cleanall
# Rebuild
bitbake core-image-minimal
cp tmp/deploy/images/qemux86-64/core-image-minimal-qemux86-64.wic build2.wic

# Compare
diffoscope build1.wic build2.wic
```

With reproducible builds enabled, `diffoscope` should report no differences. Without it, you'll see timestamp and file-order changes.

### 4. Override for a specific recipe

Create a `.bbappend` for a problematic recipe:

```bitbake
# recipes-example/foo/foo_1.0.bbappend
inherit reproducible_build

# Pin to a specific epoch if the recipe's source timestamps vary
SOURCE_DATE_EPOCH = "1719878400"
```

### 5. Debug timestamp sources

```bash
# Find all files with embedded timestamps in a package
bitbake -c devshell my-recipe
# Inside the shell:
find . -name "*.o" -exec strings {} \; | grep -E '^[A-Z][a-z]{2} [A-Z][a-z]{2} [0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2} [0-9]{4}$'
```

## Common Pitfalls & Gotchas

### 1. Host tools ignore SOURCE_DATE_EPOCH
Not all tools honor the variable. `zip`, `gzip`, and `ar` may need explicit flags. For example, `gzip -n` suppresses the original filename and timestamp. Yocto's `reproducible_build.bbclass` patches many of these, but custom recipes using host tools can break reproducibility. Always test with `diffoscope`.

### 2. sstate cache poisoning
If you build with reproducible builds enabled, then disable it, sstate may serve non-reproducible artifacts from cache. Always run `bitbake -c cleanall <recipe>` when toggling the feature, or better, use a separate `TMPDIR` for reproducible builds.

### 3. PV-based fallback is fragile
When `SOURCE_DATE_EPOCH` falls back to `PV` (e.g., "2024.07"), BitBake parses it as a timestamp. If your version string is non-numeric (e.g., "1.0+git"), the fallback fails silently, and the variable stays empty. Always explicitly set `SOURCE_DATE_EPOCH` for production releases.

## Try It Yourself

1. **Enable reproducible builds** in your `local.conf`, then build `core-image-minimal` twice. Use `diffoscope` to confirm zero differences. If you see changes, identify which recipe introduced them with `bitbake -g`.

2. **Force a fixed epoch** for a single recipe that uses `__DATE__` (e.g., `busybox`). Create a `.bbappend` that sets `SOURCE_DATE_EPOCH = "1719878400"` and verify the binary hash matches across two clean builds.

3. **Break reproducibility intentionally**: Disable `INHERIT += "reproducible_build"`, rebuild, and compare with `diffoscope`. Note the timestamp and file-ordering differences. This shows why production builds must be deterministic.

## Next Up

Tomorrow: **OTA with Yocto: SWUpdate & A/B Image Strategy** — we'll design a dual-copy update system using SWUpdate, handle rollback logic, and sign images for secure over-the-air delivery.
