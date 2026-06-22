---
title: "Day 09: Package Groups & RDEPENDS: Runtime Dependencies"
date: 2026-06-22
tags: ["til", "yocto", "package-groups", "rdepends"]
---

## What I Explored Today

Today I dug into how Yocto handles runtime dependencies between packages—specifically through `RDEPENDS` and the `packagegroup` recipe type. While build-time dependencies (`DEPENDS`) ensure headers and libraries are available during compilation, runtime dependencies (`RDEPENDS`) determine what gets installed onto the target filesystem. I also explored package groups, which are meta-recipes that bundle multiple packages into logical units like "networking tools" or "debug utilities." Getting these right is critical for producing images that boot correctly without missing shared libraries or tools.

## The Core Concept

The distinction between `DEPENDS` and `RDEPENDS` is one of the most common sources of confusion for new Yocto developers. `DEPENDS` controls the build order and ensures that a recipe's build dependencies are available in the sysroot. `RDEPENDS`, on the other hand, controls what ends up on the target device at runtime.

Consider a C application that links against `libcurl`. At build time, you need `DEPENDS = "curl"` so the compiler can find headers and link against the library. But at runtime, the target needs the `libcurl` shared library installed. That's where `RDEPENDS` comes in: `RDEPENDS:${PN} = "libcurl"`.

Package groups (`packagegroup` class) are a special recipe type that exist solely to group other packages. They have no source code, no build steps—they simply declare `RDEPENDS` on a list of packages. This is how Yocto organizes features like "graphical desktop" or "development tools" without hardcoding every package into your image recipe.

The key insight: `RDEPENDS` is transitive. If package A depends on B, and B depends on C, then installing A will pull in both B and C. This is usually what you want, but it can also pull in unexpected dependencies if you're not careful.

## Key Commands / Configuration / Code

### Basic RDEPENDS in a Recipe

```bitbake
# Example: myapp_1.0.bb
SUMMARY = "My application that needs libcurl at runtime"
LICENSE = "MIT"

DEPENDS = "curl"                     # Build-time: headers & libs for linking
RDEPENDS:${PN} = "libcurl"           # Runtime: libcurl.so must be on target

SRC_URI = "file://myapp.c"
S = "${WORKDIR}"

do_compile() {
    ${CC} ${CFLAGS} ${LDFLAGS} myapp.c -o myapp -lcurl
}

do_install() {
    install -d ${D}${bindir}
    install -m 0755 myapp ${D}${bindir}
}
```

### Creating a Package Group

Package groups live in `recipes-core/packagegroups/` and use the `packagegroup` class:

```bitbake
# recipes-core/packagegroups/packagegroup-my-tools.bb
SUMMARY = "My custom tool collection"
LICENSE = "MIT"

inherit packagegroup

# Core networking tools
RDEPENDS:${PN} = " \
    iperf3 \
    tcpdump \
    netcat-openbsd \
    curl \
"

# Optional: split into sub-packages for granularity
RDEPENDS:${PN}-debug = " \
    strace \
    ltrace \
    gdb \
"

# Ensure debug tools are only for dev images
PACKAGE_ARCH = "${MACHINE_ARCH}"
```

### Using Package Groups in an Image

```bitbake
# my-image.bb
SUMMARY = "My custom image with tools"
LICENSE = "MIT"

inherit core-image

IMAGE_INSTALL = " \
    packagegroup-core-boot \
    packagegroup-my-tools \
    ${CORE_IMAGE_EXTRA_INSTALL} \
"
```

### Checking Runtime Dependencies

```bash
# See what a package will pull in at runtime
bitbake -g myapp && cat pn-depends.dot | grep myapp

# List all runtime dependencies for a specific package
bitbake -s | grep myapp
oe-pkgdata-util read-pkgdata myapp | grep RDEPENDS

# Visualize the dependency tree (install graphviz)
bitbake -g myapp && dot -Tpng pn-depends.dot -o depends.png
```

## Common Pitfalls & Gotchas

### 1. Confusing DEPENDS with RDEPENDS for Shared Libraries
The most common mistake: adding `DEPENDS = "libfoo"` but forgetting `RDEPENDS:${PN} = "libfoo"`. The build succeeds because the library is in the sysroot, but the target image fails at runtime with "cannot open shared object file." Always check: does the target need this file at runtime? If yes, add `RDEPENDS`.

### 2. Package Group Naming and Location
Package groups must follow the naming convention `packagegroup-<name>.bb` and inherit the `packagegroup` class. If you name it `my-tools.bb` without the `packagegroup-` prefix, BitBake won't treat it as a package group. Also, ensure `PACKAGE_ARCH` is set correctly—package groups are often machine-specific but should be `all` if they're truly generic.

### 3. Transitive Dependency Surprises
`RDEPENDS` is transitive, which means a simple package group can balloon your image size. For example, adding `RDEPENDS = "python3"` pulls in Python's entire runtime, including modules you may not need. Use `oe-pkgdata-util` to inspect what a package actually depends on before adding it to your image. Consider using `RRECOMMENDS` for optional dependencies that can be safely dropped to save space.

### 4. Package Splitting and RDEPENDS
When a recipe produces multiple packages (e.g., `${PN}-dev`, `${PN}-dbg`, `${PN}-doc`), BitBake automatically adds `RDEPENDS` between them. The `-dev` package depends on `${PN}`, and `${PN}` depends on `${PN}-dbg` if debug symbols are enabled. If you override `PACKAGES` manually, you must also manage these runtime dependencies yourself.

## Try It Yourself

1. **Create a package group for network diagnostics**: Write a `packagegroup-network-diag.bb` that includes `iperf3`, `mtr`, `traceroute`, and `nmap`. Add it to your local image and verify the tools are present on the target.

2. **Inspect transitive dependencies**: Pick a recipe in your layer (e.g., `openssh`). Run `bitbake -g openssh` and examine `pn-depends.dot`. Identify three runtime dependencies that are pulled in transitively. Document why each is needed.

3. **Fix a missing runtime dependency**: Create a simple recipe that links against `libz`. Intentionally omit `RDEPENDS` and build an image. Boot the image and observe the runtime error. Then add the correct `RDEPENDS` and verify the fix.

## Next Up

Tomorrow we'll dive into **BitBake Classes: inherit, autotools, cmake, systemd**—the reusable building blocks that save you from writing boilerplate. We'll explore how `inherit autotools` handles configure/make/install for you, how `cmake` wraps CMake projects, and how `systemd` integrates service files into your recipes.
