---
title: "Day 08: do_compile & do_install: Build & Stage Tasks"
date: 2026-06-22
tags: ["til", "yocto", "do-compile", "do-install"]
---

## What I Explored Today

Today I dug into the two most critical tasks in any Yocto recipe: `do_compile` and `do_install`. While `do_fetch` and `do_patch` get the source ready, `do_compile` is where the actual build happens, and `do_install` is where we stage the output for packaging. I spent the day understanding how BitBake orchestrates these tasks, what the default implementations do, and how to override them properly when writing custom recipes.

## The Core Concept

The separation between `do_compile` and `do_install` exists for a fundamental reason: **build isolation**. In Yocto, the build output from `do_compile` lands in `${B}` (the build directory), while `do_install` copies only the necessary artifacts into `${D}` (the destination directory, typically `${WORKDIR}/image`). This separation ensures that packaging only includes what you explicitly stage, not every intermediate object file or build artifact.

Think of it this way: `do_compile` is the "make" phase, and `do_install` is the "make install" phase, but with full control. The default `do_compile` runs `oe_runmake`, which respects `${EXTRA_OEMAKE}` and `${PARALLEL_MAKE}`. The default `do_install` runs `oe_runmake install` with `DESTDIR=${D}`. When that default doesn't work—and it often doesn't for embedded cross-compilation—you override these tasks.

The key insight: **never install directly from `${S}`**. Always build into `${B}` first, then install from `${B}` into `${D}`. This keeps your source tree clean and allows out-of-tree builds.

## Key Commands / Configuration / Code

### Minimal Override Example

Here's a recipe that builds a simple C program with explicit `do_compile` and `do_install`:

```bitbake
# recipes-example/hello/hello_1.0.bb
SUMMARY = "Simple hello world program"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://hello.c"

S = "${WORKDIR}"
B = "${WORKDIR}/build"

do_compile() {
    # Use CC from the environment (set by Yocto cross-compilation)
    # ${CC} includes --sysroot and other flags
    mkdir -p ${B}
    cd ${B}
    ${CC} ${CFLAGS} ${LDFLAGS} -o hello ${S}/hello.c
}

do_install() {
    # Install into ${D} — this becomes the package root
    install -d ${D}${bindir}
    install -m 0755 ${B}/hello ${D}${bindir}/hello
}
```

### Using Autotools (common pattern)

For autotools-based projects, the defaults usually work, but you often need to tweak:

```bitbake
# recipes-example/libfoo/libfoo_1.0.bb
inherit autotools

# Pass cross-compilation flags
EXTRA_OECONF = "--enable-shared --disable-static"

# Override install to strip debug symbols (default behavior)
do_install:append() {
    # Remove .la files to avoid libtool archive pollution
    find ${D} -name "*.la" -delete
}
```

### Manual Staging with `do_install:append`

When you need to install additional files not handled by `make install`:

```bitbake
do_install:append() {
    # Install a config file that the upstream Makefile doesn't handle
    install -d ${D}${sysconfdir}
    install -m 0644 ${S}/config/default.conf ${D}${sysconfdir}/myapp.conf

    # Install a helper script
    install -d ${D}${datadir}/${BPN}/scripts
    install -m 0755 ${S}/scripts/helper.sh ${D}${datadir}/${BPN}/scripts/
}
```

### Debugging Build Failures

When `do_compile` fails, inspect the log:

```bash
# View the full log
bitbake -c compile -f myrecipe
less tmp/work/*/myrecipe/temp/log.do_compile

# Run the compile step manually in the build directory
bitbake -c devshell myrecipe
# Now you're in a shell with the cross-compilation environment
make -C ${B}
```

## Common Pitfalls & Gotchas

### 1. Forgetting `-f` flag when re-running compile

If you change source code or recipe variables, BitBake's hash equivalence may think nothing changed. Always use `-f` (force) to re-run `do_compile`:

```bash
bitbake -c compile -f myrecipe
```

Without `-f`, BitBake may skip the task entirely, leaving you confused about why your changes didn't take effect.

### 2. Installing into wrong paths

The most common mistake: hardcoding `/usr/local` or `/opt` instead of using `${D}${bindir}`, `${D}${libdir}`, etc. These variables are set by the Yocto environment and ensure files land in the correct staging directory. Hardcoding paths breaks the entire packaging pipeline.

```bitbake
# WRONG — installs to /usr/local/bin on the host during build
do_install() {
    install -m 0755 ${B}/hello /usr/local/bin/
}

# CORRECT — stages into the package root
do_install() {
    install -d ${D}${bindir}
    install -m 0755 ${B}/hello ${D}${bindir}/
}
```

### 3. Not cleaning `do_install` output between builds

Yocto doesn't automatically clean `${D}` between `do_install` runs unless you use `-c clean` or `-f`. If your install task appends files, old files from previous builds may persist. Always ensure your `do_install` starts with a clean slate or explicitly removes old files:

```bitbake
do_install:prepend() {
    # Remove any previous install artifacts
    rm -rf ${D}
}
```

## Try It Yourself

1. **Create a recipe with manual compile/install**: Write a recipe for a single-file C program that doesn't use autotools or cmake. Override both `do_compile` and `do_install` using `${CC}` and `${CFLAGS}`. Build it and verify the binary appears in `tmp/work/*/packages-split/`.

2. **Debug a failed install**: Intentionally break your `do_install` by using a wrong path (e.g., `${D}/usr/bin` instead of `${D}${bindir}`). Run `bitbake -c install -f myrecipe` and inspect the log to see the error. Fix it and confirm the package builds.

3. **Add a post-install script**: Extend a recipe with `do_install:append` to install a configuration file and a README into `${docdir}`. Verify the files appear in the final package by checking `tmp/deploy/rpm/*.rpm` contents.

## Next Up

Tomorrow we'll explore **Package Groups & RDEPENDS: Runtime Dependencies**. You'll learn how to bundle multiple recipes into a single installable unit, declare runtime dependencies between packages, and avoid the dreaded "missing shared library" errors at boot time.
