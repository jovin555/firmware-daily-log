---
title: "Day 01: Essential File Operations & Permissions"
date: 2026-06-13
tags: ["til", "lfcs", "files", "permissions"]
---

## What I Explored Today

Today I kicked off the LFCS prep by revisiting the bedrock of Linux file operations and permissions. I worked through `ls`, `chmod`, `chown`, `umask`, and the special permission bits (SUID, SGID, sticky bit) — not just the syntax, but how they interact with process execution and shared directories. The goal was to internalize why permissions matter beyond "read/write/execute" and how they enforce security boundaries in multi-user systems.

## The Core Concept

File permissions in Linux aren't just about restricting access — they're about defining trust boundaries between users, groups, and processes. Every file has an owner and a group, and three permission triads (owner, group, others) control read, write, and execute access. But the real power lies in the special bits: SUID allows a process to run with the file owner's privileges (think `passwd` updating `/etc/shadow`), SGID on directories ensures new files inherit the directory's group (critical for shared project directories), and the sticky bit prevents users from deleting each other's files in `/tmp`.

The `umask` is often misunderstood — it's not a permission set, but a mask that subtracts permissions from the default (usually 666 for files, 777 for directories). A `umask 022` means "remove write for group and others," resulting in 644 for files and 755 for directories. Understanding this prevents accidental world-writable files.

## Key Commands / Configuration / Code

```bash
# 1. List files with detailed permissions, owner, group, and SELinux context
ls -laZ /etc/passwd
# Output: -rw-r--r--. 1 root root 1234 Jun 13 10:00 /etc/passwd
# The first char is file type (-=regular, d=directory, l=symlink)

# 2. Change permissions using symbolic mode (more readable than octal)
chmod u+x script.sh          # Add execute for owner
chmod g-w,o-r file.txt       # Remove write for group, read for others
chmod a=rx public_dir/       # Set read+execute for everyone (owner, group, others)

# 3. Change permissions using octal mode (precise, no ambiguity)
chmod 755 script.sh          # rwxr-xr-x
chmod 640 config.conf        # rw-r-----
chmod 4755 suid_binary       # rwsr-xr-x (SUID set, execute becomes 's')

# 4. Change owner and group recursively
chown -R developer:devteam /var/www/project/
# -R is recursive; use with caution on large trees

# 5. Set SGID on a shared directory so new files inherit group
chmod g+s /shared/project/
# New files created here will have group = /shared/project/'s group

# 6. Set sticky bit on /tmp (prevents users from deleting others' files)
chmod +t /tmp
# Equivalent: chmod 1777 /tmp  (1 = sticky bit, 777 = full permissions)

# 7. View and set umask
umask                    # Show current mask (e.g., 0022)
umask 007                # Set mask: owner+group full, others none
# To make permanent, add to ~/.bashrc or /etc/profile:
echo "umask 027" >> ~/.bashrc

# 8. Find files with SUID/SGID (security audit)
find /usr -perm /4000 -type f 2>/dev/null   # SUID binaries
find /usr -perm /2000 -type f 2>/dev/null   # SGID binaries
```

## Common Pitfalls & Gotchas

1. **Octal mode confusion with special bits**: `chmod 4755` sets SUID, but `chmod 755` does not. The leading digit (4=SUID, 2=SGID, 1=sticky) is often forgotten. Always double-check with `ls -l` — SUID shows as `s` in owner execute position, SGID as `s` in group execute position.

2. **`chown` requires root, but `chgrp` may not**: Only root can change file ownership. However, a user can change the group of a file they own to any group they belong to (`chgrp`). This trips up engineers who try `chown user:group` as a non-root user — it fails silently or with "Operation not permitted."

3. **`umask` affects new files, not existing ones**: Changing `umask` mid-session only affects files created afterward. Also, `umask` is a mask, not a permission set — `umask 022` does *not* mean "give 022 permissions." It means "remove write for group and others." Beginners often set `umask 000` thinking it's safe, but that creates world-writable files.

## Try It Yourself

1. **Shared directory with SGID**: Create a directory `/tmp/lab_shared`, set group to `users` (or your primary group), apply SGID (`chmod g+s`), and set permissions to `2775`. Create a file inside as a non-root user and verify its group matches the directory's group, not your primary group.

2. **SUID binary audit**: Run `find /usr/bin -perm /4000 -type f` and examine three results. Use `ls -l` to confirm the `s` in owner execute position. Check one binary's purpose with `man` or `strings` — why does it need elevated privileges?

3. **Umask experiment**: Set `umask 077`, then create a file with `touch test.txt` and a directory with `mkdir testdir`. Check permissions with `ls -l`. Then set `umask 000`, create another file, and compare. Explain why the directory got `700` and the file got `600`.

## Next Up

Tomorrow I'll dive into **Hard Links, Symbolic Links & readlink** — understanding the difference between directory entries and inodes, why hard links can't cross filesystems, and how `readlink` resolves symlink chains. We'll also cover the practical gotcha of broken symlinks in deployment scripts.
