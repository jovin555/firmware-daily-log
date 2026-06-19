---
title: "Day 07: Fetchers: SRC_URI for Git, HTTP, Local & Patches"
date: 2026-06-19
tags: ["til", "yocto", "src-uri", "fetcher", "patches"]
---

## What I Explored Today

Today I dove into the Yocto fetcher subsystem — the engine behind `SRC_URI` that pulls source code into your build. I’ve used `git://` and `http://` URLs before, but I never fully understood the fetcher architecture: how BitBake resolves URIs, fetches from remote sources, caches downloads in `DL_DIR`, and applies patches. I also learned how to mix local files with upstream tarballs and how to handle authentication for private repos. This is the backbone of every recipe, and getting it right saves hours of debugging.

## The Core Concept

The `SRC_URI` variable is a list of URIs that BitBake’s fetcher module processes sequentially. Each URI scheme (e.g., `git://`, `http://`, `file://`) maps to a specific fetcher class. The fetcher downloads (or copies) the source into the `DL_DIR` (download directory), then unpacks it into the `WORKDIR` during the `do_fetch` and `do_unpack` tasks.

Why does this matter? Because Yocto is designed for offline builds and repeatability. The fetcher ensures that every source artifact is cached locally, checksummed against `SRC_URI[sha256sum]`, and can be reused across builds. If you’re working with a team, you can share a common `DL_DIR` to avoid redundant downloads. Patches are also handled via `SRC_URI` — they’re applied after unpacking, before any build steps.

The key insight: `SRC_URI` isn’t just a list of URLs; it’s a declarative specification of *how* to obtain and prepare source code. The fetcher handles branching, submodules, authentication, and even shallow clones for Git repos.

## Key Commands / Configuration / Code

### 1. Git Fetcher — Branch, Tag, and Commit

```bitbake
# Fetch a specific tag from a Git repo
SRC_URI = "git://git.example.com/myproject.git;protocol=https;branch=main;tag=v1.2.3"

# Fetch a specific commit (most reproducible)
SRC_URI = "git://git.example.com/myproject.git;protocol=ssh;branch=develop;rev=abc123def456"

# Shallow clone to save bandwidth (Yocto Kirkstone+)
SRC_URI = "git://git.example.com/myproject.git;protocol=https;nobranch=1;rev=abc123;depth=1"
```

**Important**: Always set `SRCREV` to pin the revision when using Git. Without it, BitBake fetches `HEAD` of the branch, which is non-reproducible.

```bitbake
SRCREV = "abc123def456"
SRC_URI = "git://git.example.com/myproject.git;protocol=https;branch=main"
```

### 2. HTTP Fetcher — Tarballs and Archives

```bitbake
# Standard tarball with checksum
SRC_URI = "https://example.com/releases/myapp-1.0.tar.gz"
SRC_URI[sha256sum] = "a1b2c3d4e5f6..."

# With custom download filename (avoids URL-based naming)
SRC_URI = "https://example.com/download?file=myapp.tar.gz;downloadfilename=myapp-1.0.tar.gz"
```

### 3. Local Files — `file://` Scheme

```bitbake
# Copy a local file from the recipe's directory (FILESPATH)
SRC_URI = "file://myconfig.cfg"

# Copy from a subdirectory in the layer
SRC_URI = "file://patches/fix-issue.patch"

# Multiple local files
SRC_URI = " \
    file://init-script.sh \
    file://default.conf \
    "
```

Local files are searched in `FILESPATH`, which by default includes the recipe directory and `files/` subdirectory.

### 4. Patches — Applying Modifications

```bitbake
# Patches are just file:// URIs; BitBake applies them automatically
SRC_URI = " \
    https://example.com/source-1.0.tar.gz \
    file://0001-fix-build.patch \
    file://0002-add-feature.patch;patchdir=src/subdir \
    "
```

Patches are applied in order. The `patchdir` parameter applies the patch relative to a subdirectory inside the source tree.

### 5. Authentication for Private Repos

```bitbake
# For Git over HTTPS with username/password (use .netrc or git config)
# In local.conf or recipe:
SRC_URI = "git://github.com/myorg/private-repo.git;protocol=https;user=myuser:${MY_PASSWORD}"

# For SSH keys, ensure SSH agent is running or use key file:
SRC_URI = "git://git@github.com/myorg/private-repo.git;protocol=ssh"
```

**Better practice**: Use `BB_GIT_SHALLOW` and `BB_GIT_SHALLOW_DEPTH` in `local.conf` for large repos.

## Common Pitfalls & Gotchas

1. **Missing `SRCREV` with Git fetcher**  
   If you specify a branch but no `SRCREV`, BitBake fetches the latest commit at build time. This breaks reproducibility. Always pin `SRCREV` to a full SHA (40 hex chars) or a tag.

2. **Patch ordering and conflicts**  
   Patches are applied in the order listed in `SRC_URI`. If two patches modify the same file, the second one may fail. Use `quilt` or `devtool` to manage patch stacks. Also, patches must be generated from the exact source version — a patch for v1.0 won’t apply cleanly to v1.1.

3. **Local file not found**  
   The `file://` fetcher searches `FILESPATH`, which includes `BPN` and `PN` directories. If you put a file in the wrong location (e.g., `recipes-myapp/myapp/files/` vs `recipes-myapp/myapp/`), BitBake won’t find it. Use `bitbake -e myapp | grep ^FILESPATH` to debug.

## Try It Yourself

1. **Create a recipe that fetches a Git repo at a specific tag**  
   Write a recipe for a simple tool (e.g., `hello-world` from GitHub). Set `SRC_URI` with `git://`, `branch=main`, and `tag=v1.0`. Verify that `bitbake -c fetch hello-world` downloads the correct commit.

2. **Add a local patch to an existing recipe**  
   Take any recipe that fetches a tarball (e.g., `zlib`). Create a `.patch` file that changes a comment in the source. Add it to `SRC_URI` and confirm it applies by running `bitbake -c patch zlib` and inspecting the source in `WORKDIR`.

3. **Test authentication with a private Git repo**  
   If you have access to a private repo, configure SSH keys or a `.netrc` file. Write a recipe that fetches from it using `protocol=ssh`. Run `bitbake -c fetch -v myprivaterepo` and watch the fetcher authenticate.

## Next Up

Tomorrow we move from fetching to building: `do_compile` and `do_install`. I’ll cover how Yocto orchestrates the compilation step, how to override the default build system (autotools, cmake, meson), and how to stage files into the sysroot for other recipes to use. We’ll also look at `D` and `DESTDIR` — the key to getting `do_install` right.
