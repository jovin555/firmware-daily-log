---
title: "Day 03: BitBake Fundamentals: Tasks, Recipes & Execution Model"
date: 2026-06-15
tags: ["til", "yocto", "bitbake", "tasks", "recipes"]
---

## What I Explored Today

Today I dug into the heart of the Yocto build system: BitBake's execution model. I've been treating `bitbake core-image-minimal` as a magic incantation, but today I forced myself to understand what actually happens when that command runs. The answer: BitBake parses recipes, resolves dependencies, and executes a directed acyclic graph (DAG) of tasks. Understanding this flow is the difference between cargo-culting Yocto and actually being able to debug build failures, optimize build times, and write correct recipes.

## The Core Concept

BitBake is not a build system in the traditional Make sense. It's a task scheduler with a functional dependency resolver. Every recipe (`.bb` file) defines a set of tasks — `do_fetch`, `do_unpack`, `do_patch`, `do_configure`, `do_compile`, `do_install`, and `do_package` are the canonical ones. Each task has dependencies on other tasks, both within the same recipe and across recipes.

The key insight: BitBake doesn't execute recipes; it executes tasks. When you run `bitbake my-recipe`, BitBake:
1. Parses all recipes in the layer search path
2. Builds a dependency graph of every task across every recipe
3. Schedules tasks for execution, respecting dependencies
4. Caches task outputs (stamps) to avoid re-executing unchanged tasks

This is fundamentally different from Make, where you target files. BitBake targets tasks, and the task graph is computed at parse time, not execution time. The `do_build` task is the default target for a recipe — it depends on all other tasks in the correct order.

## Key Commands / Configuration / Code

Let's get hands-on. First, inspect what tasks a recipe actually has:

```bash
# List all tasks for a recipe
bitbake -c listtasks zlib

# Show the dependency graph for a specific task
bitbake -g zlib -c compile
# This generates task-depends.dot and pn-depends.dot
# View with: xdot task-depends.dot
```

The real power comes from understanding how tasks are defined and extended. Here's a minimal recipe with a custom task:

```bitbake
# recipes-example/hello/hello_1.0.bb
DESCRIPTION = "A simple hello world recipe"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://hello.c"

# BitBake automatically provides do_fetch, do_unpack, do_configure
# We only need to define do_compile and do_install

do_compile() {
    ${CC} ${CFLAGS} ${LDFLAGS} ${WORKDIR}/hello.c -o ${B}/hello
}

do_install() {
    install -d ${D}${bindir}
    install -m 0755 ${B}/hello ${D}${bindir}
}

# Add a custom informational task
do_print_details() {
    bbnote "Recipe: ${PN}, Version: ${PV}"
    bbnote "Work directory: ${WORKDIR}"
    bbnote "Target sysroot: ${STAGING_DIR_TARGET}"
}
addtask do_print_details after do_compile before do_install
```

To execute just your custom task:

```bash
bitbake -c print_details hello
```

Now let's look at how BitBake handles task dependencies across recipes. This is critical for understanding build ordering:

```bitbake
# recipes-example/consumer/consumer_1.0.bb
DEPENDS = "hello"

do_configure() {
    # hello's do_populate_sysroot must have run before this
    # because DEPENDS ensures hello's staging is available
    if [ -f ${STAGING_BINDIR_NATIVE}/hello ]; then
        bbnote "hello binary found in staging"
    fi
}
```

The `DEPENDS` variable creates an implicit task dependency: `do_configure` of `consumer` depends on `do_populate_sysroot` of `hello`.

## Common Pitfalls & Gotchas

**1. Task ordering via `addtask` without proper `after`/`before`**
I've seen builds fail because someone added a custom task with `addtask do_mytask` but didn't specify ordering. BitBake will still schedule it, but at an unpredictable point. Always use `after` and `before` to anchor your task in the known task chain. If you don't, your task might run before `do_unpack` and try to access files that don't exist yet.

**2. Confusing `DEPENDS` with `RDEPENDS`**
`DEPENDS` controls build-time task ordering and populates the sysroot. `RDEPENDS` controls runtime package dependencies. A common mistake: setting `RDEPENDS` and expecting the build system to fetch and compile the dependency. It won't — `RDEPENDS` only affects the package metadata. Use `DEPENDS` for build dependencies, `RDEPENDS` for runtime.

**3. Ignoring the stamp file mechanism**
BitBake uses stamp files to track task completion. If you manually modify files in `tmp/work/` and re-run a build, BitBake won't re-execute tasks because the stamps are still valid. Use `bitbake -c clean <recipe>` or `bitbake -C <task> <recipe>` to force re-execution. The `-C` flag is particularly useful: it invalidates the specified task and all tasks that depend on it.

## Try It Yourself

1. **Visualize the task graph**: Run `bitbake -g core-image-minimal` and examine the generated `task-depends.dot` file. Use `grep` to find all tasks related to `zlib`. Then install `xdot` or use `dot -Tpng` to render the graph. Identify the longest dependency chain you can find.

2. **Create a recipe with a custom task**: Write a recipe that fetches a simple text file, then adds a custom task `do_validate` that checks the file's checksum after `do_fetch` but before `do_unpack`. Use `bbfatal` to fail the build if the checksum doesn't match. Run `bitbake -c validate <your-recipe>` to test.

3. **Debug a task dependency issue**: Create two recipes where recipe B depends on recipe A. In recipe A's `do_install`, write a file to `${D}${datadir}/data.txt`. In recipe B's `do_configure`, try to read that file from `${STAGING_DATADIR}`. Observe what happens when you build B without A being built first. Then add the correct `DEPENDS` and observe the difference.

## Next Up

Tomorrow we'll explore how layers work — the architecture that keeps Yocto projects organized. We'll dive into `bblayers.conf`, layer priority, and how BitBake resolves recipe conflicts when multiple layers provide the same recipe. This is where Yocto's composability really shines, and where most "layer hell" problems originate.
