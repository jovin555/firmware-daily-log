---
title: "Day 10: BitBake Classes: inherit, autotools, cmake, systemd"
date: 2026-06-22
tags: ["til", "yocto", "inherit", "classes"]
---

## What I Explored Today

Today I dug into BitBake's class inheritance system—specifically how `inherit` works and the three most critical classes in any Yocto build: `autotools`, `cmake`, and `systemd`. After weeks of writing recipes from scratch, I realized I was reinventing the wheel. Classes are the framework's way of saying "don't write boilerplate, reuse battle-tested patterns." I spent the morning tracing through `meta/classes-recipe/` to understand exactly what each class injects into the build process.

## The Core Concept

BitBake classes are essentially prepackaged task logic. When you write `inherit autotools`, you're not just importing a file—you're pulling in dozens of carefully ordered tasks, variable defaults, and dependency chains. The `inherit` directive works like a mixin: it appends the class's content into your recipe's namespace at parse time.

Why does this matter? Because build systems have deep conventions. Autotools expects `configure.ac`, `Makefile.am`, and a specific `./configure` invocation. CMake expects `CMakeLists.txt` and generator flags. Systemd expects unit files in specific locations. Each class encodes those expectations so you don't have to manually set `EXTRA_OECONF`, `OECMAKE_SOURCEPATH`, or `SYSTEMD_SERVICE` every single time.

The real power is composition. You can `inherit autotools systemd` in one recipe, and BitBake merges both class behaviors. The order matters—later inherits can override variables from earlier ones—but the system handles most conflicts gracefully.

## Key Commands / Configuration / Code

### The `inherit` directive

```bitbake
# Simple inheritance
inherit autotools

# Multiple classes
inherit autotools systemd

# Conditional inheritance (rare, but exists)
inherit ${@bb.utils.contains('DISTRO_FEATURES', 'systemd', 'systemd', '', d)}
```

### Autotools class in action

```bitbake
# meta/recipes-support/libpcap/libpcap_1.10.4.bb
SUMMARY = "System-independent interface for user-level packet capture"
LICENSE = "BSD-3-Clause"
LIC_FILES_CHKSUM = "file://LICENSE;md5=..."

# This single line does ALL of the following:
# - Adds autotools to PACKAGECONFIG
# - Sets do_configure to run ./configure with proper --host, --target
# - Sets do_compile to run make with parallel jobs
# - Sets do_install to run make install with DESTDIR
# - Handles cross-compilation sysroot paths
inherit autotools

# You only need to add custom flags
EXTRA_OECONF = "--enable-ipv6"
```

### CMake class example

```bitbake
# meta/recipes-devtools/cmake/cmake-native_3.28.1.bb
inherit cmake

# CMake class automatically:
# - Sets CMAKE_SYSTEM_NAME to Linux
# - Sets CMAKE_C_COMPILER to the cross-compiler
# - Passes OECMAKE_SOURCEPATH (defaults to ${S})
# - Adds cmake-native to DEPENDS

# Override the source directory if needed
OECMAKE_SOURCEPATH = "${S}/src"

# Pass additional CMake flags
EXTRA_OECMAKE = "-DBUILD_TESTING=OFF -DCMAKE_BUILD_TYPE=Release"
```

### Systemd class integration

```bitbake
# Example recipe with systemd service
SUMMARY = "Custom daemon"
LICENSE = "MIT"

inherit autotools systemd

# Tell systemd class about our service file
SRC_URI += "file://mydaemon.service"

SYSTEMD_SERVICE:${PN} = "mydaemon.service"
SYSTEMD_AUTO_ENABLE = "enable"

# The class automatically:
# - Installs .service files to ${systemd_system_unitdir}
# - Adds systemd to DEPENDS if DISTRO_FEATURES has systemd
# - Handles enable/disable in postinst/prerm scripts
# - Sets FILES:${PN} to include the unit files
```

### Checking what a class actually does

```bash
# See the full class content
bitbake-layers show-recipes -f myrecipe | grep -A5 "inherit"

# Or read the class directly
cat meta/classes-recipe/autotools.bbclass | head -100

# Debug what variables a class sets
bitbake -e myrecipe | grep "^EXTRA_OECONF="
```

## Common Pitfalls & Gotchas

**1. Inheriting without the corresponding build tool in DEPENDS**
The `cmake` class expects `cmake-native` to be in `DEPENDS`, but it doesn't always add it automatically if you override `inherit` order. Always verify: `bitbake -e myrecipe | grep "^DEPENDS="`. If cmake-native is missing, add `DEPENDS += "cmake-native"` explicitly.

**2. Systemd class and non-systemd DISTRO_FEATURES**
If your distro doesn't include `systemd` in `DISTRO_FEATURES`, the `systemd` class is essentially a no-op. Your service files won't be installed, and you'll get confusing errors. Check with `bitbake -e | grep DISTRO_FEATURES` before debugging further.

**3. Autotools class with out-of-tree builds**
By default, `autotools` does out-of-tree builds into `${B}`. If your software has hardcoded paths or expects in-tree builds, you'll get "cannot find config.status" errors. Set `B = "${S}"` to force in-tree, but this is a last resort—fix the software instead.

**4. Class ordering matters for variable overrides**
When you write `inherit autotools cmake`, the `cmake` class's `do_configure` will override `autotools`'s. If you need both, you must write a custom `do_configure` that calls both. Use `addtask` and `do_configure[depends]` to chain them properly.

## Try It Yourself

1. **Trace a class's impact**: Pick any recipe that inherits `autotools`. Run `bitbake -e <recipe> | grep -E "^(do_configure|do_compile|do_install)"` and compare the output to the same recipe without the `inherit` line (create a copy in your layer). Note the task signatures change.

2. **Convert a Makefile recipe to CMake**: Find a simple recipe using `inherit autotools`. Replace it with `inherit cmake`, update `SRC_URI` to point to a CMake-based project, and fix `EXTRA_OECONF` to `EXTRA_OECMAKE`. Build and verify.

3. **Add systemd support to an existing recipe**: Take a recipe that installs a daemon binary. Add `inherit systemd`, create a `.service` file in your layer, set `SYSTEMD_SERVICE`, and verify the service is packaged with `bitbake -c package <recipe>` and checking `packages-split/<pn>/`.

## Next Up

Tomorrow I'm tackling **Machine Configuration: MACHINE, TUNE & BSP Layers**. We'll explore how Yocto knows what CPU you're building for, how tune files encode ARMv7 vs ARMv8 vs x86-64 microarchitecture flags, and why BSP layers are the backbone of hardware support. Expect deep dives into `conf/machine/`, `tune-*.inc` files, and the art of writing a machine config that doesn't break.
