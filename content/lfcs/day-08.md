---
title: "Day 08: Archiving with tar: Creation, Extraction & Compression"
date: 2026-06-22
tags: ["til", "lfcs", "tar", "compression"]
---

## What I Explored Today

Today I went deep into `tar` — the Tape ARchiver — which is the Swiss Army knife of file archiving on Linux. While `tar` originally wrote data to tape drives, it's now the standard tool for bundling files into a single archive (a "tarball") and optionally compressing them. I focused on the three operations that matter most in daily engineering work: creating archives, extracting them, and applying compression algorithms (gzip, bzip2, xz). I also learned why `tar` is almost always preferred over `zip` for Unix-to-Unix transfers, especially when preserving permissions, ownership, and metadata.

## The Core Concept

`tar` does two things: it concatenates files and directories into a single byte stream (the archive), and it can optionally pipe that stream through a compression filter. The key insight is that `tar` itself does **not** compress — it delegates compression to external programs like `gzip`, `bzip2`, or `xz`. The `-z`, `-j`, and `-J` flags are just convenience wrappers that call those programs.

Why does this matter? Because you can chain `tar` with any compression tool, or even skip compression entirely when you need speed (e.g., for incremental backups). The archive format also preserves Unix file metadata (permissions, ownership, timestamps, ACLs, extended attributes) that `zip` often loses. For LFCS, you must be comfortable with both the long-form and short-form flags, and understand that the order of `-c`, `-f`, and the archive name is positional.

## Key Commands / Configuration / Code

### Creating a tar archive (no compression)
```bash
# Create archive of /var/log, verbose, output to logs.tar
tar -cvf logs.tar /var/log
# -c: create, -v: verbose (list files), -f: specify archive file
```

### Creating compressed archives
```bash
# gzip compression (fast, moderate compression)
tar -czvf logs.tar.gz /var/log

# bzip2 compression (slower, better compression)
tar -cjvf logs.tar.bz2 /var/log

# xz compression (slowest, best compression ratio)
tar -cJvf logs.tar.xz /var/log
```

### Extracting archives
```bash
# Extract to current directory (auto-detects compression)
tar -xvf logs.tar.gz

# Extract to specific directory
tar -xvf logs.tar.gz -C /tmp/restored

# Extract only specific files (wildcards supported)
tar -xvf logs.tar.gz --wildcards '*.log'
```

### Listing contents without extracting
```bash
# List files in archive (no extraction)
tar -tvf logs.tar.gz
# -t: list table of contents
```

### Using compression manually (advanced)
```bash
# Equivalent to tar -czvf, but explicit
tar -cvf - /var/log | gzip > logs.tar.gz

# Decompress and extract in one pipeline
xzcat logs.tar.xz | tar -xvf -
```

### Preserving permissions and ownership (for system backups)
```bash
# --same-owner preserves UID/GID (requires root)
sudo tar -cvpf backup.tar /etc
# -p: preserve permissions (default when root)
```

## Common Pitfalls & Gotchas

1. **Forgetting the `-f` flag** — If you write `tar -cvz archive.tar.gz /path`, tar interprets `archive.tar.gz` as a file to add to the archive, not the archive name. The `-f` must immediately precede the archive filename. Correct: `tar -czvf archive.tar.gz /path`.

2. **Relative vs. absolute paths** — When you create an archive with absolute paths (e.g., `tar -cvf backup.tar /home/user`), extracting will recreate the full path. This can overwrite system files. Always use relative paths or strip leading `/` with `--transform`:
   ```bash
   tar -cvf backup.tar --transform 's/^\///' /home/user
   ```

3. **Compression algorithm mismatch** — `tar` auto-detects compression on extraction, but if you rename a `.tar.gz` to `.tar.xz`, extraction will fail. Always keep the correct extension: `.tar.gz` (gzip), `.tar.bz2` (bzip2), `.tar.xz` (xz). For maximum portability, stick with gzip — it's universally available.

## Try It Yourself

1. **Create a compressed backup of your home directory** (excluding hidden files) and verify its integrity:
   ```bash
   tar -czvf home_backup.tar.gz --exclude='.*' ~/
   tar -tzvf home_backup.tar.gz | head -20
   ```

2. **Extract a single file from a tarball** without extracting the entire archive. Download a sample tarball (e.g., a Linux kernel source) and extract only the `README` file:
   ```bash
   tar -xvf linux-6.1.tar.xz linux-6.1/README -C /tmp
   ```

3. **Compare compression ratios** for the same directory using gzip, bzip2, and xz. Time each operation with `time` and check sizes with `ls -lh`:
   ```bash
   time tar -czvf test.tar.gz /usr/share/doc
   time tar -cjvf test.tar.bz2 /usr/share/doc
   time tar -cJvf test.tar.xz /usr/share/doc
   ```

## Next Up

Tomorrow I'm tackling **I/O Redirection, Pipes, `tee` & `xargs`** — the plumbing that connects commands together. We'll cover stdin/stdout/stderr redirection, process substitution, and how to chain commands like a pro. See you then.
