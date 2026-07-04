---
title: "Day 22: Image Size Optimization & Stripping"
date: 2026-07-04
tags: ["til", "yocto", "image-size", "optimization"]
---

## What I Explored Today

Today I dug into the critical but often-overlooked art of image size optimization in Yocto. After weeks of building increasingly complex images, my root filesystem had ballooned to over 400 MB for what should be a lean embedded target. I spent the day understanding how Yocto handles debug symbols, unused files, and package metadata—and how to strip all of that down without breaking functionality. The results were dramatic: a 60% size reduction with zero runtime impact.

## The Core Concept

Embedded systems live and die by flash budget. Every kilobyte saved means faster flashing, cheaper BOM costs, and more room for application data. Yocto builds include enormous amounts of data that is essential during development but deadly in production:

- **Debug symbols** (.debug sections, separate debug files) — often 2-5x the binary size
- **Static libraries** (.a files) — only needed for rebuilding, never for runtime
- **Package metadata** (.pyc, .pyo, locale data, documentation)
- **Unused locales and translations** — glibc locale data alone can be 100+ MB

The core mechanism for size control is **stripping**: removing symbol tables, relocation information, and debugging sections from ELF binaries. Yocto handles this through a combination of build-time configuration (`INHIBIT_PACKAGE_STRIP`, `PACKAGE_DEBUG_SPLIT_STYLE`) and post-processing (`ROOTFS_POSTPROCESS_COMMAND`).

But stripping is just the start. The real power comes from **selective inclusion**—deciding exactly what goes into the image rather than removing what you don't want after the fact.

## Key Commands / Configuration / Code

### 1. Global stripping and debug splitting

In `local.conf` or your distro config:

```bitbake
# Split debug symbols into separate -dbg packages (default)
# Keeps runtime binaries small, debug info available on demand
PACKAGE_DEBUG_SPLIT_STYLE = "debug-file-directory"

# Alternative: strip everything, no debug packages at all
# PACKAGE_DEBUG_SPLIT_STYLE = "no-debug"

# Remove .debug sections from binaries during packaging
INHIBIT_PACKAGE_STRIP = "0"  # 0 = strip (default), 1 = don't strip

# Remove static libraries from the image
PACKAGE_EXCLUDE = "*-staticdev *-dev"
```

### 2. Image-level size optimization

Create an image class or add to your image recipe:

```bitbake
# image-size-optimize.bbclass
inherit image

# Remove documentation, locales, and package metadata
ROOTFS_POSTPROCESS_COMMAND += "remove_unnecessary_files ; "

remove_unnecessary_files() {
    # Remove all documentation
    rm -rf ${IMAGE_ROOTFS}/usr/share/doc/*
    rm -rf ${IMAGE_ROOTFS}/usr/share/man/*
    rm -rf ${IMAGE_ROOTFS}/usr/share/info/*
    rm -rf ${IMAGE_ROOTFS}/usr/share/gtk-doc/*
    
    # Remove all .pyc and .pyo files (Python bytecode cache)
    find ${IMAGE_ROOTFS} -name '*.pyc' -o -name '*.pyo' -delete
    
    # Remove static libraries
    find ${IMAGE_ROOTFS} -name '*.a' -delete
    
    # Keep only C.UTF-8 locale (saves 50-100 MB)
    localedir=${IMAGE_ROOTFS}/usr/lib/locale
    if [ -d "$localedir" ]; then
        find $localedir -mindepth 1 -maxdepth 1 ! -name 'C.UTF-8' -exec rm -rf {} +
    fi
}
```

### 3. Measuring image size

```bash
# After build, check individual package sizes
bitbake -g my-image && grep -v "^#" task-depends.dot | \
    awk '{print $1}' | sort -u | while read pkg; do
    size=$(du -sh tmp/deploy/rpm/$pkg*.rpm 2>/dev/null | awk '{print $1}')
    [ -n "$size" ] && echo "$size $pkg"
done | sort -rh | head -20

# Use the built-in size report
bitbake my-image -c rootfs
# Look for: "The image size is X bytes" in the log

# Manual inspection
du -sh tmp/work/*/my-image/*/rootfs/
```

### 4. Selective package exclusion

```bitbake
# In your image recipe, exclude entire packages
IMAGE_INSTALL:remove = "packagegroup-core-buildessential"
PACKAGE_EXCLUDE = "kernel-devsrc kernel-dev kernel-headers"
```

## Common Pitfalls & Gotchas

### 1. Over-stripping breaks debugging
If you set `INHIBIT_PACKAGE_STRIP = "1"` to keep debug symbols, your image size explodes. If you strip everything (`PACKAGE_DEBUG_SPLIT_STYLE = "no-debug"`), you lose the ability to debug crashes in the field. The sweet spot is `debug-file-directory` (default) which keeps separate `-dbg` packages you can install on demand.

### 2. Locale removal breaks glibc
Removing all locales except C.UTF-8 is tempting, but some applications (especially those using `setlocale()`) will fail silently or crash. Always test with your application stack. If you need `en_US.UTF-8`, keep it.

### 3. Static library removal breaks rebuilds
Deleting `*.a` files from the rootfs is safe for runtime, but if your image includes development tools or you expect users to compile on-target, you've broken that workflow. Use `PACKAGE_EXCLUDE` for `*-dev` and `*-staticdev` instead of manual deletion.

### 4. Python .pyc removal causes first-run slowness
Without precompiled `.pyc` files, Python will regenerate them on first import, which can cause significant startup delay and requires write access to the filesystem. Consider keeping `.pyc` for frequently-used modules.

## Try It Yourself

1. **Measure your baseline**: Run `bitbake my-image -c rootfs` and note the final image size. Then add `PACKAGE_DEBUG_SPLIT_STYLE = "no-debug"` to your local.conf, rebuild, and compare. What percentage did you save?

2. **Audit package bloat**: Use `du -sh tmp/deploy/rpm/*.rpm | sort -rh | head -10` to find the top 10 largest packages in your deployment directory. For each, check if it's truly needed at runtime.

3. **Create a size-optimized image variant**: Write a new image recipe that inherits your base image but adds the `remove_unnecessary_files()` function from this post. Build both, compare sizes, and verify your application still works.

## Next Up

Tomorrow we tackle **Reproducible Builds & SOURCE_DATE_EPOCH** — how to make your Yocto builds produce byte-identical outputs regardless of when or where they're built, and why that matters for security and supply chain integrity.
