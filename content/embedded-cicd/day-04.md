---
title: "Day 04: Build Caching Strategies: ccache & Artifact Reuse Across Pipelines"
date: 2026-07-04
tags: ["til", "embedded-cicd", "ccache", "build-cache"]
---

## What I Explored Today

Today I dug into the practical side of build caching for embedded systems, specifically how to stop recompiling the same object files across pipeline runs. I set up `ccache` with a cross-compiler toolchain, configured artifact caching in GitLab CI and GitHub Actions, and measured the wall-clock savings on a real firmware project. The result: a full rebuild dropped from 12 minutes to under 90 seconds on a cache hit.

## The Core Concept

Embedded builds are slow because every compilation unit must be processed through the preprocessor, compiler, and assembler. When you change one `.c` file, the entire project doesn't need to recompile—only the objects whose dependencies changed. But CI pipelines are ephemeral: each run starts from a clean workspace. Without caching, you pay the full rebuild cost every time.

Build caching solves this at two levels:

1. **Compiler-level caching (ccache):** Intercepts calls to `gcc`, `clang`, or your cross-compiler. It hashes the preprocessed source, compiler flags, and include paths. If the hash matches a previous compilation, it copies the cached `.o` file instead of running the compiler. This works transparently—you just prepend `ccache` to your compiler command.

2. **Pipeline-level artifact caching:** Stores compiled object files, static libraries, or even the final binary between pipeline runs. The CI runner downloads the cache at the start of the job and uploads a fresh one at the end. This is essential for monorepos or projects with long link times.

The key insight: ccache handles *incremental* changes within a single pipeline stage, while artifact caching handles *cross-pipeline* reuse. Use both, but understand their tradeoffs. ccache is CPU-efficient but has a fixed-size cache directory. Artifact caching is storage-intensive but can be shared across branches.

## Key Commands / Configuration / Code

### 1. Setting up ccache for a cross-compiler

```bash
# Install ccache
sudo apt-get install ccache

# Configure ccache for a 5GB cache, compression enabled
ccache --max-size=5G
ccache --set-config=compression=true

# Wrap your cross-compiler
export CC="ccache arm-none-eabi-gcc"
export CXX="ccache arm-none-eabi-g++"

# Verify it's working
ccache --zero-stats
make -j4
ccache --show-stats
# Expected output:
# cache hit (direct)                   42
# cache hit (preprocessed)              8
# cache miss                           12
# files in cache                      62
```

### 2. GitLab CI artifact caching for object files

```yaml
# .gitlab-ci.yml
variables:
  CCACHE_DIR: "${CI_PROJECT_DIR}/.ccache"
  CCACHE_MAXSIZE: "5G"

stages:
  - build

build_firmware:
  stage: build
  script:
    - ccache --zero-stats
    - make -j$(nproc)
    - ccache --show-stats
  cache:
    key: "${CI_COMMIT_REF_SLUG}-ccache"
    paths:
      - .ccache/
    policy: pull-push
  artifacts:
    paths:
      - build/*.elf
      - build/*.hex
    expire_in: 1 week
```

### 3. GitHub Actions with ccache and sccache (Rust alternative)

```yaml
# .github/workflows/build.yml
name: Firmware Build

on: [push]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install ccache
        run: sudo apt-get install ccache

      - name: Cache ccache
        uses: actions/cache@v3
        with:
          path: ~/.ccache
          key: ${{ runner.os }}-ccache-${{ hashFiles('**/*.c', '**/*.h', 'Makefile') }}
          restore-keys: |
            ${{ runner.os }}-ccache-

      - name: Build
        run: |
          export CC="ccache arm-none-eabi-gcc"
          export CXX="ccache arm-none-eabi-g++"
          make -j$(nproc)
```

### 4. Handling linker output caching (advanced)

For large projects, even linking is slow. Cache the final `.elf` if the object files haven't changed:

```bash
# In your Makefile, add a cached link step
LINK_CACHE := build/.link_cache

build/firmware.elf: $(OBJECTS)
	@if [ -f $(LINK_CACHE) ] && [ "$(shell cat $(LINK_CACHE))" = "$(shell md5sum $(OBJECTS) | md5sum)" ]; then \
		echo "Link cache hit, copying..."; \
		cp build/firmware.elf.cached $@; \
	else \
		$(LD) $(LDFLAGS) -o $@ $(OBJECTS) $(LIBS); \
		cp $@ build/firmware.elf.cached; \
		md5sum $(OBJECTS) | md5sum > $(LINK_CACHE); \
	fi
```

## Common Pitfalls & Gotchas

1. **Debug info and timestamps break ccache hashing.** If your build embeds `__DATE__`, `__TIME__`, or `__FILE__` with absolute paths, every build will be a cache miss. Use `-ffile-prefix-map` to strip paths, and avoid `__DATE__`/`__TIME__` in production builds. Alternatively, set `CCACHE_SLOPPINESS=file_macro,time_macros` to ignore them.

2. **Cache key collisions in CI.** Using branch name alone as the cache key means feature branches never share caches. Use a hash of your build configuration files (Makefile, CMakeLists.txt, toolchain file) as the primary key, with the branch name as a fallback. This maximizes hits across branches with identical build setups.

3. **ccache doesn't cache linker output.** It only caches compilation (`.c` → `.o`). The link step still runs every time. For large projects, implement a manual linker cache as shown above, or use a build system like Meson that supports link caching natively.

4. **Cache invalidation on toolchain updates.** If you update your cross-compiler, all cached objects become invalid. Always include the toolchain version in your cache key. A simple `gcc --version | head -1` piped into the key works.

## Try It Yourself

1. **Profile your current build:** Run `make clean && time make -j4` to get your baseline. Then enable ccache with `export CC="ccache $(CC)"` and run `make -j4` again. Compare the times and check `ccache --show-stats` for hit rate.

2. **Set up CI artifact caching:** Pick your CI platform (GitLab, GitHub Actions, Jenkins) and add a cache step for your build output directory. Use a composite key that includes your Makefile hash and toolchain version. Run two consecutive pipeline triggers—the second should be significantly faster.

3. **Eliminate timestamp macros:** Search your codebase for `__DATE__` and `__TIME__`. Replace them with a build ID from your CI system (e.g., `GIT_COMMIT` or `BUILD_NUMBER`). Verify that ccache hit rate improves by at least 20%.

## Next Up

Tomorrow we’ll dive into **Compiler Optimization Flags: -O2 vs -Os in a CI Pipeline**—how to choose the right optimization level for embedded targets, measure code size vs. performance tradeoffs, and automate flag selection based on build type (debug vs. release).
