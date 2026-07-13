---
title: "Day 31: Package Management: apt, dpkg, rpm, dnf"
date: 2026-07-13
tags: ["til", "lfcs", "packages", "apt"]
---

## What I Explored Today

Today I dove into the four pillars of Linux package management: `apt`/`dpkg` on Debian-based systems and `dnf`/`rpm` on Red Hat-based systems. While the high-level tools (`apt`, `dnf`) handle dependency resolution and repository interaction, the low-level tools (`dpkg`, `rpm`) operate directly on `.deb` and `.rpm` files. Understanding both layers is critical for troubleshooting broken installs, auditing installed packages, and working across distributions in mixed environments.

## The Core Concept

Package management exists to solve three problems: dependency hell, upgrade safety, and auditability. High-level tools (`apt`, `dnf`) abstract away the graph of dependencies—they fetch, resolve, and install everything in the correct order. Low-level tools (`dpkg`, `rpm`) are the atomic units: they unpack archives, run pre/post-install scripts, and track metadata. The key insight: **never use low-level tools to install packages with unresolved dependencies** unless you know exactly what you're doing. Use them for inspection, extraction, and emergency surgery when the high-level tool is broken.

## Key Commands / Configuration / Code

### Debian/Ubuntu: `apt` and `dpkg`

```bash
# Update package index (always do this first)
sudo apt update

# Upgrade all packages safely
sudo apt upgrade

# Full upgrade (handles changed dependencies, may remove packages)
sudo apt full-upgrade

# Search for a package
apt search nginx

# Show detailed info before installing
apt show nginx

# Install with automatic dependency resolution
sudo apt install nginx

# Remove package (leaves config files)
sudo apt remove nginx

# Purge package (removes config too)
sudo apt purge nginx

# Remove orphaned dependencies
sudo apt autoremove

# Low-level: query installed .deb packages
dpkg -l | grep nginx

# List files owned by a package
dpkg -L nginx

# Find which package owns a file
dpkg -S /etc/nginx/nginx.conf

# Low-level install (NO dependency resolution — use with caution)
sudo dpkg -i some-package.deb

# Fix broken dependencies after a dpkg install
sudo apt --fix-broken install

# Extract contents of a .deb without installing
dpkg-deb -x package.deb /tmp/extracted
```

### Red Hat/Fedora: `dnf` and `rpm`

```bash
# Update all packages
sudo dnf update

# Search repositories
dnf search nginx

# Show package info
dnf info nginx

# Install with dependencies
sudo dnf install nginx

# Remove package
sudo dnf remove nginx

# List installed packages
dnf list installed

# List available groups
dnf group list

# Install a group (e.g., "Development Tools")
sudo dnf group install "Development Tools"

# Low-level: query all installed RPMs
rpm -qa

# Query specific package info
rpm -qi nginx

# List files in package
rpm -ql nginx

# Find package owning a file
rpm -qf /etc/nginx/nginx.conf

# Low-level install (no deps — dangerous)
sudo rpm -ivh package.rpm

# Upgrade with rpm (also no dep resolution)
sudo rpm -Uvh package.rpm

# Verify package integrity (checksum, permissions, etc.)
rpm -V nginx
```

### Configuration Files

```bash
# Debian: repository sources
cat /etc/apt/sources.list
ls /etc/apt/sources.list.d/

# Red Hat: repository configuration
cat /etc/yum.repos.d/*.repo
# or for DNF
cat /etc/dnf/dnf.conf
```

## Common Pitfalls & Gotchas

1. **`dpkg -i` without `apt --fix-broken`** — Installing a `.deb` manually with `dpkg -i` will fail if dependencies are missing. The package is left in a "half-installed" state. Always follow with `sudo apt --fix-broken install` to resolve the graph. If you forget, `dpkg --configure -a` can retry configuration.

2. **`apt upgrade` vs `apt full-upgrade`** — `apt upgrade` never removes packages or installs new ones; it only upgrades existing ones. `apt full-upgrade` (or `apt dist-upgrade`) may remove packages to satisfy dependency changes. On production systems, run `apt upgrade` first, then review what `full-upgrade` would change.

3. **`rpm -e` removing critical system packages** — RPM has no dependency checking by default. Running `rpm -e glibc` will happily delete your C library, breaking every binary on the system. Always use `dnf remove` (or `yum remove`) which checks the dependency tree. If you must use `rpm -e`, add `--test` to dry-run first.

4. **Mixing `apt` and `snap`/`flatpak`** — Modern systems often have multiple package managers. A package installed via `snap` won't show up in `dpkg -l` or `apt list --installed`. Use `snap list` and `flatpak list` separately. This can cause confusion when troubleshooting "missing" commands.

## Try It Yourself

1. **Inspect a package without installing it**: Download any `.deb` or `.rpm` (e.g., from packages.debian.org). Use `dpkg-deb --info` or `rpm -qip` to view metadata, then `dpkg-deb -R` or `rpm2cpio` to extract the contents to a temp directory. Examine the control scripts.

2. **Recover from a broken dpkg install**: On a Debian VM, download a `.deb` with unmet dependencies and run `sudo dpkg -i` on it. Observe the error. Then run `sudo apt --fix-broken install` to resolve. Verify with `dpkg -l | grep ^i`.

3. **Find the source of a config file**: On any system, pick a config file in `/etc` (e.g., `/etc/ssh/sshd_config`). Use `dpkg -S` or `rpm -qf` to find which package owns it. Then use `dpkg -L` or `rpm -ql` to list all files from that package. Note which files are marked as "conffiles" (Debian) or "%config" (RPM).

## Next Up: Disk Partitioning: fdisk, gdisk

Tomorrow we'll move from software packages to disk layout. We'll cover `fdisk` for MBR partitioning, `gdisk` for GPT, and how to create, delete, and resize partitions without losing data. You'll learn why GPT is preferred for disks over 2TB and how to align partitions for SSD performance.
