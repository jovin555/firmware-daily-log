---
title: "Day 20: Shared State Cache (sstate): Speed Up Builds"
date: 2026-07-02
tags: ["til", "yocto", "sstate", "cache"]
---

## What I Explored Today

Today I dove into the Shared State Cache (sstate) — the mechanism that makes incremental Yocto builds tolerable. After weeks of watching full rebuilds take hours, I finally understood how sstate avoids redundant work, how to configure it properly, and why my builds sometimes mysteriously "rebuilt everything" despite no code changes. The payoff is immediate: properly configured sstate can reduce a 45-minute rebuild to under 5 minutes.

## The Core Concept

Yocto's BitBake is fundamentally a task executor. Every recipe has tasks like `do_fetch`, `do_unpack`, `do_configure`, `do_compile`, `do_install`, and `do_package`. Without sstate, changing one line in a `.c` file triggers a full re-execution of every downstream task — even if those tasks produce identical output.

The Shared State Cache solves this by hashing the *inputs* to each task. Before running a task, BitBake computes a checksum of everything that influences that task's output: the recipe metadata, the source code, the toolchain version, the dependencies' outputs, and even the build configuration variables. If the checksum matches a previously completed task's hash, BitBake skips the task entirely and restores the output from the sstate cache.

This is not just a "cache" in the traditional sense. It's a content-addressable store where the key is a cryptographic hash of the task's complete input set. This means:
- **Safe skipping**: If any input changes, the hash changes, and the task re-runs.
- **Cross-build sharing**: Two different machines building the same recipe with the same inputs share the same sstate objects.
- **Partial rebuilds**: Changing only a library's source code invalidates only that library's tasks and its direct dependents — not the entire system.

## Key Commands / Configuration / Code

### 1. Configuring sstate directories

In your `local.conf` or `distro.conf`:

```bitbake
# Local sstate cache (always set this)
SSTATE_DIR = "${TOPDIR}/sstate-cache"

# Shared sstate mirror (network-accessible, e.g., NFS or HTTP)
SSTATE_MIRRORS = "file://.* http://sstate-server.example.com/sstate/PATH"

# Optional: compress sstate to save space (xz is default)
SSTATE_MANIFESTS = "${TOPDIR}/sstate-manifests"
```

### 2. Checking sstate cache hits/misses

The most useful debugging command:

```bash
# Show detailed sstate status for a specific recipe
bitbake -S printdiff my-image

# Check what's in the cache without building
bitbake -S none my-image

# See sstate stats after a build (look for "Sstate summary")
bitbake my-image
# Output example:
# Sstate summary: Wanted 342 Found 321 Missed 21 Current 0 (94% match, 6% incomplete)
```

### 3. Manually populating the sstate cache

When setting up a new build environment or CI pipeline:

```bash
# Pre-populate sstate for a specific target
bitbake --runall build my-image

# Generate sstate packages for all recipes (useful for mirrors)
bitbake meta-toolchain -c populate_sdk
bitbake my-image -c populate_sstate
```

### 4. Invalidating specific sstate entries

When you know a cache entry is stale (e.g., after changing a global config):

```bash
# Force re-run of specific tasks for a recipe
bitbake -c cleanall openssl
bitbake -c fetch openssl    # Re-fetch
bitbake -c compile openssl  # Re-compile

# Or use the sstate-cache-management script
sstate-cache-management.sh --remove-duplicated --cache-dir=${SSTATE_DIR}
```

### 5. Understanding hash equivalence

Modern Yocto (Thud+) uses hash equivalence to further optimize sstate:

```bitbake
# In local.conf
BB_HASHSERVE = "auto"
BB_HASHSERVE_DB = "${TOPDIR}/hashserv.db"
```

This allows BitBake to recognize that two different compilations produce identical output binaries, even if the input hashes differ slightly (e.g., due to timestamps).

## Common Pitfalls & Gotchas

1. **The "sstate cache poisoning" trap**: If you share sstate between different build configurations (e.g., debug vs. release, or different MACHINE values), you'll get corrupted builds. Always use separate SSTATE_DIR per configuration, or ensure your SSTATE_MIRRORS includes the build configuration in the URL path. The sstate hash includes MACHINE, TUNE_FEATURES, and DISTRO — but not your local.conf comments.

2. **The "invisible rebuild" gotcha**: Changing a variable in `local.conf` that's not part of the task hash (e.g., `PACKAGE_CLASSES`) won't trigger a rebuild, but the sstate output may be incompatible. Always run `bitbake -S printdiff` after configuration changes to see what actually changed.

3. **The "sstate explosion" problem**: Over time, sstate directories can grow to tens of gigabytes. Use `SSTATE_MANIFESTS` to track which entries are still referenced, and periodically run `sstate-cache-management.sh --remove-duplicated`. For CI systems, set `SSTATE_DIR` to a temporary directory and only keep the final sstate packages.

## Try It Yourself

1. **Measure your current sstate hit rate**: Run `bitbake core-image-minimal` on a clean build directory, then immediately run it again. Compare the build times and look for "Sstate summary" in the output. The second build should show >95% hit rate.

2. **Create a shared sstate mirror**: Set up an HTTP server (e.g., `python3 -m http.server 8000` in your sstate directory) and configure `SSTATE_MIRRORS` in a second build directory. Run a build on the second machine and verify it downloads sstate packages instead of rebuilding.

3. **Debug a cache miss**: Add `INHERIT += "buildstats"` to `local.conf`, build a recipe, then use `bitbake -S printdiff <recipe>` to see exactly which inputs changed between two builds. This is invaluable for understanding why your CI sometimes rebuilds everything.

## Next Up: BitBake Debugging: -DDD, buildhistory & dep graphs

Tomorrow, I'll tackle the three tools every Yocto engineer needs when builds go wrong: the `-DDD` debug flag for tracing BitBake's decision-making, `buildhistory` for tracking output changes over time, and dependency graphs for visualizing why your recipe depends on that one library you've never heard of.
