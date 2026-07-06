---
title: "Day 06: Semantic Versioning & Changelogs for Firmware Releases"
date: 2026-07-06
tags: ["til", "embedded-cicd", "semver", "changelog"]
---

## What I Explored Today

Today I tackled the surprisingly thorny problem of versioning firmware releases in a CI/CD pipeline. Unlike web apps where you can hot-patch a server, embedded firmware gets flashed onto devices that may sit in the field for years. Getting versioning wrong means bricked updates, impossible debugging, and angry customers. I implemented semantic versioning (SemVer 2.0.0) with automated changelog generation using `git-cliff` and `cargo-bump` for our Rust-based firmware, then wired it into our GitLab CI pipeline to tag releases automatically.

## The Core Concept

Semantic versioning for firmware follows the `MAJOR.MINOR.PATCH` format, but embedded systems add critical nuance. A MAJOR bump means breaking hardware compatibility—different pinouts, changed register maps, or new bootloader requirements. MINOR bumps add features while maintaining backward compatibility with the same hardware revision. PATCH bumps fix bugs with zero behavioral changes to existing APIs.

The real insight: firmware versioning must be *machine-readable* and *field-auditable*. Your bootloader needs to parse the version to decide if an OTA update is allowed. Your support team needs to look at a device's reported version and immediately know what changed. This is why we store the version string in a dedicated memory section (`.version_info`) that survives firmware updates, and why we generate changelogs automatically from conventional commits—no manual editing, no forgotten entries.

## Key Commands / Configuration / Code

### 1. Git-Cliff Configuration for Firmware Changelogs

`git-cliff` parses conventional commit messages and generates structured changelogs. Here's our `.cliff.toml` tailored for embedded releases:

```toml
# cliff.toml
[changelog]
header = "# Changelog\n\nAll notable changes to this firmware project will be documented in this file.\n"
body = """
{% for group, commits in commits | group_by(attribute="group") %}
### {{ group | upper_first }}
{% for commit in commits %}
- {{ commit.message | upper_first }}{% if commit.breaking %} **BREAKING**{% endif %}
{% endfor %}
{% endfor %}
"""
# Trim whitespace for clean output
trim = true

[git]
# Only consider commits that affect firmware source, not docs or CI config
conventional_commits = true
filter_unconventional = true
# Ignore commits that only touch non-firmware paths
skip_commits_that_modify = ["docs/*", ".gitlab-ci.yml", "README.md"]
# Parse scopes like "hal", "ble", "bootloader" for grouping
commit_parsers = [
    { message = "^feat", group = "Features" },
    { message = "^fix", group = "Bug Fixes" },
    { message = "^perf", group = "Performance" },
    { message = "^refactor", group = "Refactoring" },
    { message = "^docs", group = "Documentation", skip = true },
    { message = "^ci", group = "CI/CD", skip = true },
]
```

### 2. Automated Version Bump in CI (GitLab)

This job runs on the `main` branch after merge. It reads the conventional commit message to determine bump type, then tags the release:

```yaml
# .gitlab-ci.yml snippet
bump-version:
  stage: release
  only:
    - main
  script:
    # Install git-cliff and cargo-bump (for Rust projects)
    - cargo install git-cliff cargo-bump
    # Determine bump type from the merge commit message
    - |
      COMMIT_MSG=$(git log -1 --pretty=%B)
      if echo "$COMMIT_MSG" | grep -q "BREAKING CHANGE"; then
        BUMP_TYPE="major"
      elif echo "$COMMIT_MSG" | grep -q "^feat"; then
        BUMP_TYPE="minor"
      else
        BUMP_TYPE="patch"
      fi
    # Bump version in Cargo.toml and create git tag
    - cargo bump $BUMP_TYPE
    - VERSION=$(cargo metadata --format-version=1 --no-deps | jq -r '.packages[0].version')
    - git-cliff -o CHANGELOG.md --tag "$VERSION"
    - git add Cargo.toml CHANGELOG.md
    - git commit -m "chore(release): v$VERSION"
    - git tag -a "v$VERSION" -m "Release v$VERSION"
    - git push origin main --tags
```

### 3. Embedding Version in Firmware Binary

We store the version in a dedicated linker section so the bootloader can read it without parsing ELF headers:

```c
// version_info.c — compiled into firmware
#include <stdint.h>

// This struct is placed in its own section at a fixed address
typedef struct __attribute__((packed)) {
    uint32_t magic;        // 0xDEADBEEF for validation
    uint16_t major;
    uint16_t minor;
    uint16_t patch;
    char     git_sha[8];   // first 8 hex chars of commit hash
    uint32_t build_timestamp;
} version_info_t;

// Place in .version_info section (defined in linker script)
__attribute__((section(".version_info")))
const version_info_t firmware_version = {
    .magic  = 0xDEADBEEF,
    .major  = MAJOR_VERSION,   // set by build system
    .minor  = MINOR_VERSION,
    .patch  = PATCH_VERSION,
    .git_sha = GIT_SHA_STRING,
    .build_timestamp = BUILD_TIMESTAMP,
};
```

## Common Pitfalls & Gotchas

**1. Forgetting that PATCH bumps can break OTA compatibility.** If you change the firmware image format, encryption scheme, or bootloader signature verification in a PATCH release, devices running the old bootloader may reject the update. Always bump MINOR if you change the update protocol, even if no API changes.

**2. Changelogs that omit hardware-specific changes.** Your changelog must note which hardware revisions (PCB rev, silicon errata) a release targets. A firmware update that works on Rev B boards may brick Rev A boards. We add a `Hardware Compatibility` section to every release note.

**3. Version strings that don't fit in the bootloader's parser.** Many MCU bootloaders have fixed-size buffers for version strings. If you use long SemVer pre-release tags like `v2.1.0-rc.3+build.20260706`, the bootloader may truncate it. Keep version strings under 32 bytes, or use a packed binary format (like the struct above) instead of ASCII.

## Try It Yourself

1. **Set up git-cliff** in your firmware repo. Write a `.cliff.toml` that ignores documentation commits and groups features, fixes, and performance changes separately. Run `git-cliff -o CHANGELOG.md` and inspect the output.

2. **Add a version info section** to your firmware. Create a linker script that places a version struct at a known flash address (e.g., `0x0800_FF00` for STM32). Write a small bootloader stub that reads and prints this version over UART.

3. **Automate the bump** in your CI. Add a job that reads the last commit message, determines if it's a major/minor/patch change, and tags the release. Push a test commit with `BREAKING CHANGE` in the message and verify the tag is `v2.0.0` (or whatever your current major is +1).

## Next Up

Tomorrow we dive into **Artifact Repositories: Storing & Signing Firmware Binaries**. We'll set up a private artifact store (using GitLab Package Registry or AWS S3), sign firmware images with hardware-backed keys (HSM or TPM), and implement a verification step in the bootloader. No more "which .bin file did we ship to production?" panic.
