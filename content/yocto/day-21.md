---
title: "Day 21: BitBake Debugging: -DDD, buildhistory & dep graphs"
date: 2026-07-03
tags: ["til", "yocto", "debugging", "bitbake"]
---

## What I Explored Today

Today I dove deep into three essential debugging techniques that every Yocto engineer needs when things go sideways: BitBake's verbose logging with `-DDD`, the buildhistory class for tracking what changed between builds, and dependency graph generation to untangle complex recipe relationships. These tools have saved me countless hours when debugging build failures, unexpected package versions, or mysterious dependency chains.

## The Core Concept

When a Yocto build fails or produces unexpected output, the default error messages are often too terse to diagnose the root cause. BitBake's logging levels (`-D`, `-DD`, `-DDD`) progressively reveal more internal state, from basic task execution details to full Python stack traces and variable expansion history. The `-DDD` flag is your nuclear option—it dumps everything BitBake knows about what it's doing.

Buildhistory complements this by providing a persistent record of your build outputs. Instead of wondering "what changed between last week's build and today's failure?", you can diff the buildhistory directory to see exactly which packages changed size, which files were added or removed, and which dependencies shifted.

Dependency graphs (task-level and recipe-level) solve a different problem: understanding *why* a particular recipe is being built. When you have a 2000-recipe image and something pulls in an unexpected library, `bitbake -g` generates DOT files you can render to visualize the dependency tree.

## Key Commands / Configuration / Code

**Verbose Debug Logging**

```bash
# Basic debug output - shows task execution and basic info
bitbake -D core-image-minimal

# More verbose - shows variable expansion and recipe parsing
bitbake -DD core-image-minimal

# Maximum verbosity - shows everything including Python tracebacks
bitbake -DDD core-image-minimal

# Combine with specific recipe for targeted debugging
bitbake -DDD -b /path/to/myapp.bb

# Save debug output to file for analysis
bitbake -DDD core-image-minimal 2>&1 | tee build_debug.log
```

**Buildhistory Configuration**

```conf
# In your local.conf or distro config
INHERIT += "buildhistory"
BUILDHISTORY_COMMIT = "1"
BUILDHISTORY_DIR = "${TOPDIR}/buildhistory"
BUILDHISTORY_FEATURES = "image package sdk"
```

After enabling, rebuild and check the history:

```bash
# Build with buildhistory enabled
bitbake core-image-minimal

# See what changed since last build
cd buildhistory
git diff HEAD~1 -- images/qemux86-64/glibc/core-image-minimal/

# Check package size changes
git diff HEAD~1 -- packages/qemux86-64/openssl/
```

**Dependency Graph Generation**

```bash
# Generate recipe-level dependency graph
bitbake -g core-image-minimal

# Generate task-level dependency graph (more detailed)
bitbake -g -u taskexp core-image-minimal

# Convert DOT files to PNG for visualization
dot -Tpng recipe-depends.dot -o deps.png

# Filter graph to focus on specific recipe
bitbake -g -u depexp openssl
```

The `-g` flag produces two files: `recipe-depends.dot` (recipe-level) and `pn-depends.dot` (package-level). For complex images, I often pipe through `grep` to isolate specific recipes:

```bash
# Find what depends on openssl
grep "openssl" recipe-depends.dot | grep "->"
```

## Common Pitfalls & Gotchas

**1. Buildhistory requires a clean baseline**
If you enable buildhistory mid-project without a clean build, your first commit will contain artifacts from previous builds. Always do `bitbake -c cleanall <image>` before the first buildhistory-enabled build to get a proper baseline. Otherwise, your diffs will be contaminated with stale data.

**2. `-DDD` output is overwhelming**
The maximum verbosity can produce gigabytes of log output for a full image build. I've learned to use `-DDD` only on single recipes or specific tasks. For example, `bitbake -DDD -c compile myapp` gives you the deep debug without drowning in output from 500 other recipes. Always redirect to a file.

**3. Dependency graphs don't show runtime dependencies by default**
The `-g` flag generates build-time dependency graphs. For runtime dependencies (RDEPENDS), you need to use `bitbake -g -r` or examine the generated `pn-depends.dot` file which includes both. Many engineers miss this and wonder why their graph doesn't match the actual image contents.

## Try It Yourself

**Task 1: Debug a failing recipe with -DDD**
Take a recipe that's failing to compile and run `bitbake -DDD -c compile <recipe> 2>&1 | tee debug.log`. Search for "Traceback" or "ERROR" in the output. Notice how the verbose logging shows the exact variable values and task execution order leading to the failure.

**Task 2: Set up buildhistory and diff two builds**
Add the buildhistory configuration to your `local.conf`, do a clean build of your image, then make a small change (e.g., add a package to IMAGE_INSTALL). Rebuild and run `git diff` in the buildhistory directory. Identify which files changed size and which new packages appeared.

**Task 3: Generate and analyze a dependency graph**
Run `bitbake -g core-image-minimal` and open `recipe-depends.dot`. Find a recipe you didn't expect in the build and trace its dependency chain back to your image. Use `dot -Tpng` to visualize the graph and confirm your understanding of why that recipe is being built.

## Next Up

Tomorrow we tackle **Image Size Optimization & Stripping** — reducing your root filesystem footprint by controlling debug symbols, splitting packages, and using the right compression. Your embedded device's flash will thank you.
