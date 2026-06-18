---
title: "Day 06: Writing a Recipe: .bb File Anatomy & Variables"
date: 2026-06-18
tags: ["til", "yocto", "recipe", "bb-file"]
---

## What I Explored Today

Today I dove into the anatomy of a `.bb` recipe file — the fundamental unit of metadata in Yocto. I dissected the required sections, understood how BitBake interprets variables, and learned the difference between immediate, lazy, and override-based variable assignment. I also built a minimal recipe from scratch and verified it with `bitbake-layers show-recipes`.

## The Core Concept

A `.bb` file is not a shell script or a Makefile — it’s a **metadata file** that BitBake parses to understand *what* to build, *where* to get sources, *how* to configure and compile, and *where* to install the output. The key insight is that BitBake uses a two-phase execution: first it parses all variables and functions (the “parsing” phase), then it executes tasks in dependency order (the “execution” phase). This means variable assignment semantics matter enormously.

The most common assignment operators are:
- `=` — immediate assignment (evaluated at parse time)
- `?=` — set if not already set (weak default)
- `??=` — set if not set by anything else (very weak default)
- `+=` and `=+` — append/prepend with space
- `.=` and `=.` — append/prepend without space
- `_append`, `_prepend`, `_remove` — override-style operators (evaluated at the end of parsing, after all assignments)

Understanding these is critical because the order of parsing (layer priority, include files, inherit) determines the final value of every variable.

## Key Commands / Configuration / Code

### Minimal Recipe: `recipes-example/hello/hello_1.0.0.bb`

```bitbake
# Basic metadata
SUMMARY = "A simple hello world program"
DESCRIPTION = "Prints 'Hello from Yocto!' to stdout"
HOMEPAGE = "https://example.com/hello"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://LICENSE;md5=0835ade698e0bcf8506ecda2f7b4f302"

# Source fetching — we'll cover this in depth tomorrow
SRC_URI = "file://hello.c \
           file://LICENSE"

# Source directory inside WORKDIR
S = "${WORKDIR}"

# Inherit autotools or cmake? No — we'll use a simple Makefile
inherit autotools-brokensep  # for projects without subdirectories

# Override the do_configure to do nothing (we have no configure)
do_configure[noexec] = "1"

# Custom do_compile
do_compile() {
    ${CC} ${CFLAGS} ${LDFLAGS} hello.c -o hello
}

# Install step — FILES_${PN} is set automatically
do_install() {
    install -d ${D}${bindir}
    install -m 0755 hello ${D}${bindir}
}
```

### Variable Assignment Examples

```bitbake
# Immediate assignment — value is fixed at parse time
MY_VAR = "apple"

# Weak default — only used if MY_VAR is not already set
MY_VAR ?= "banana"

# Very weak default — overridden by any ?= or = assignment
MY_VAR ??= "cherry"

# Append with space — adds " date" to the end
MY_VAR += "date"

# Prepend with space — adds "early " to the beginning
MY_VAR =+ "early"

# Override-style append — evaluated after all assignments
MY_VAR_append = " final"

# Override-style prepend
MY_VAR_prepend = "first "

# Override-style remove — removes all occurrences of "banana"
MY_VAR_remove = "banana"
```

### Checking Your Recipe

```bash
# List all recipes (including yours)
bitbake-layers show-recipes | grep hello

# Show the parsed recipe with all variables expanded
bitbake -e hello | grep ^MY_VAR=

# Build it
bitbake hello
```

## Common Pitfalls & Gotchas

1. **Confusing `_append` with `+=`**  
   `_append` is evaluated *after* all `=` assignments, even those in `.bbappend` files. `+=` is evaluated immediately. If you write `MY_VAR += "world"` in a `.bbappend`, it appends at the time the `.bbappend` is parsed — which may be before a later `MY_VAR = "hello"` in the base recipe overwrites everything. Use `_append` for layer overrides.

2. **Forgetting `S = "${WORKDIR}"` for local files**  
   If your `SRC_URI` points to `file://` entries, they are unpacked into `${WORKDIR}`. If you don’t set `S` to `${WORKDIR}`, BitBake expects a subdirectory (e.g., `hello-1.0.0`) and will fail with `do_unpack` errors. Always explicitly set `S` when using local files.

3. **Missing `LIC_FILES_CHKSUM`**  
   Yocto requires a checksum for every license file. If you omit it, `bitbake` will refuse to build. Use `md5sum` to generate the hash, or let BitBake tell you the expected value (it prints the error with the correct hash).

## Try It Yourself

1. **Create a recipe from scratch** for a simple C program that prints “Hello Yocto!”. Use `file://` for the source, set `S = "${WORKDIR}"`, and implement `do_compile` and `do_install`. Build it with `bitbake <recipe-name>`.

2. **Experiment with variable assignment** by adding a `.bbappend` file that changes `SUMMARY` using both `+=` and `_append`. Run `bitbake -e` to see the final value and understand the difference.

3. **Break it intentionally**: Remove `LIC_FILES_CHKSUM` and observe the error. Then fix it by adding the correct checksum. This builds muscle memory for the required metadata fields.

## Next Up

Tomorrow we’ll dive into **Fetchers: SRC_URI for Git, HTTP, Local & Patches**. You’ll learn how to pull source from remote repositories, apply patches, and handle tarballs — the backbone of any real-world recipe.
