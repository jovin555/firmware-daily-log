---
title: "Day 01: Yocto Overview: OpenEmbedded, Poky & BitBake"
date: 2026-06-13
tags: ["til", "yocto", "yocto", "openembedded", "poky"]
---

## What I Explored Today

I finally sat down to untangle the Yocto Project ecosystem. For months, I'd heard colleagues throw around terms like "Poky," "BitBake," and "OpenEmbedded" as if they were interchangeable. They're not. Today I mapped the actual architecture: Yocto is the umbrella project, OpenEmbedded is the build system, BitBake is the task executor, and Poky is the reference distribution that ties them together. Understanding these layers is the difference between blindly running `bitbake core-image-minimal` and knowing exactly what happens when you do.

## The Core Concept

The Yocto Project isn't a single tool—it's a collaboration framework. Think of it as a layered cake:

- **Bottom layer: OpenEmbedded (OE)** — The build system. It provides the metadata (recipes, classes, configurations) that describe how to fetch, patch, compile, and package software. OE is the engine.
- **Middle layer: BitBake** — The task scheduler and executor. It reads OE metadata and decides the order of operations (fetch → patch → configure → compile → install → package). BitBake is the driver.
- **Top layer: Poky** — A reference distribution maintained by the Yocto Project. It bundles a specific version of OE metadata, BitBake, and a default set of recipes to produce a minimal Linux system. Poky is the "hello world" of embedded Linux builds.

Why this separation matters: You can use OE metadata without Poky. You can swap BitBake for another scheduler (though nobody does). You can create your own distribution layer on top of Poky. This modularity is what makes Yocto portable across hardware—ARM, x86, RISC-V, you name it.

The real magic is **layering**. Each layer (e.g., `meta-raspberrypi`, `meta-ti`) adds recipes and configurations without modifying the core. Your custom layer sits on top, overriding only what you need. This is how a single build system supports hundreds of boards.

## Key Commands / Configuration / Code

Let's start with the minimal build. After setting up Poky (we'll cover that tomorrow), you'll run:

```bash
# Source the build environment (sets up PATH, creates build directory)
source oe-init-build-env build

# Inside the build directory, inspect the default target
bitbake -s | grep core-image-minimal
# Output: core-image-minimal:1.0-r0

# Build a minimal image (takes 30-60 minutes first time)
bitbake core-image-minimal
```

The real work happens in `conf/local.conf` and `conf/bblayers.conf`. Here's a typical `local.conf` snippet:

```bash
# conf/local.conf
# Target machine (e.g., qemuarm64, raspberrypi3, beaglebone)
MACHINE ?= "qemuarm64"

# Number of parallel threads (set to your CPU cores)
BB_NUMBER_THREADS = "8"
PARALLEL_MAKE = "-j 8"

# Enable additional package formats
PACKAGE_CLASSES ?= "package_rpm package_deb package_ipk"

# Add a custom layer (must also be in bblayers.conf)
# This tells BitBake to look for recipes in meta-mylayer
```

And `bblayers.conf`:

```bash
# conf/bblayers.conf
BBLAYERS ?= " \
  /path/to/poky/meta \
  /path/to/poky/meta-poky \
  /path/to/poky/meta-yocto-bsp \
  /path/to/meta-mylayer \
  "
```

To understand what BitBake is doing, inspect a recipe:

```bash
# Find the recipe for bash
bitbake -e bash | grep ^SRC_URI
# Output: SRC_URI="http://ftp.gnu.org/gnu/bash/bash-5.2.tar.gz ..."

# Show the dependency tree
bitbake -g bash && cat task-depends.dot | grep bash
```

The `-e` flag is your best friend—it dumps the entire environment for a recipe after all variable expansions. When something breaks, `bitbake -e <recipe> | grep ^ERROR_QA` will show you QA checks.

## Common Pitfalls & Gotchas

1. **Confusing Poky with Yocto.** Poky is a *reference* distribution, not the project itself. If you say "I'm building Yocto," you're technically wrong. You're building a Poky-based distribution using the Yocto Project tools. This distinction matters when filing bugs—upstream maintainers will ask "which layer?" not "which Yocto version?"

2. **Ignoring the SSTATE_DIR.** BitBake caches build artifacts in `SSTATE_DIR` (default: `build/sstate-cache`). If you delete your build directory but keep `SSTATE_DIR`, rebuilds are fast. If you delete both, you're rebuilding the world. Set `SSTATE_DIR` to a persistent location outside your build directory.

3. **Running `bitbake` without sourcing the environment.** The `oe-init-build-env` script sets critical variables like `TMPDIR`, `DL_DIR`, and `BBPATH`. Running `bitbake` from a fresh terminal without sourcing it will fail with cryptic errors about missing metadata. Always source first.

## Try It Yourself

1. **Explore the layer structure.** Clone Poky (`git clone git://git.yoctoproject.org/poky`), then run `bitbake-layers show-layers` to see the default layers. Add a dummy layer with `bitbake-layers create-layer meta-mytest` and inspect the generated `conf/layer.conf`.

2. **Trace a recipe's dependencies.** Pick a simple recipe like `zlib`. Run `bitbake -g zlib` and open `recipe-depends.dot` in a graph viewer (or just `grep` for dependencies). Identify which recipes are build-time only vs. runtime.

3. **Modify a local configuration.** In `conf/local.conf`, change `MACHINE` to `qemux86-64` and rebuild `core-image-minimal`. Compare the build output—notice how BitBake reuses the SSTATE for unchanged components but rebuilds architecture-specific packages.

## Next Up

Tomorrow, we set up a real Yocto build environment from scratch—no shortcuts, no pre-built SDKs. We'll use `kas` to automate the layer configuration and build process, turning a 30-minute manual setup into a 2-minute YAML file. You'll have a bootable QEMU image by the end of Day 2.
