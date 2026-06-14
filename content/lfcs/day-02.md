---
title: "Day 02: Hard Links, Symbolic Links & readlink"
date: 2026-06-14
tags: ["til", "lfcs", "links", "inodes"]
---

## What I Explored Today

Today I dug into one of the most misunderstood yet fundamental concepts in the Linux filesystem: links. Hard links and symbolic (soft) links are everywhere—from shared libraries to backup strategies—but I've seen even senior engineers misuse them. I spent the day tracing inode tables, breaking symlink chains, and understanding exactly when each type of link is appropriate. The `readlink` command, often overlooked, turned out to be the key to debugging link resolution in scripts.

## The Core Concept

At the filesystem level, a file isn't its name. A file is an **inode**—a data structure storing metadata (permissions, timestamps, block pointers) and a unique number. Directory entries are just mappings from names to inode numbers. This is the key insight.

**Hard links** create another directory entry pointing to the *same* inode. The file's data isn't duplicated; you just have two names for the same underlying object. The inode's link count tracks how many names exist. When it drops to zero, the data is freed. Hard links cannot cross filesystem boundaries (inodes are unique per filesystem) and cannot link to directories (to prevent cycles).

**Symbolic links** are tiny files whose content is a path string. When the kernel resolves a symlink, it reads that path and follows it. Symlinks can point anywhere—different filesystems, directories, or even non-existent targets (dangling symlinks). They have their own inode and permissions, but those are usually ignored; the target's permissions matter.

The practical difference: hard links are *indistinguishable* from the original (no "this is a link" metadata), while symlinks are explicit pointers that can break.

## Key Commands / Configuration / Code

### Creating and Inspecting Hard Links

```bash
# Create a file and a hard link
echo "LFCS Day 2" > original.txt
ln original.txt hardlink.txt

# Both point to the same inode
ls -li original.txt hardlink.txt
# Output (inode numbers will match):
# 123456 -rw-r--r-- 2 user user 10 Jun 14 10:00 original.txt
# 123456 -rw-r--r-- 2 user user 10 Jun 14 10:00 hardlink.txt

# The '2' after permissions is the link count
stat original.txt | grep Links
# Output: Links: 2
```

### Creating and Resolving Symbolic Links

```bash
# Create a symbolic link
ln -s /etc/hostname hostname_link

# Inspect it
ls -l hostname_link
# Output: lrwxrwxrwx 1 user user 13 Jun 14 10:05 hostname_link -> /etc/hostname

# The 'l' at the front means symlink; size is path length (13 bytes)

# readlink shows the target WITHOUT following it
readlink hostname_link
# Output: /etc/hostname

# readlink -f resolves the full canonical path (follows all symlinks)
readlink -f hostname_link
# Output: /etc/hostname  (or actual path if /etc/hostname is itself a symlink)

# For relative symlinks, -f is essential
ln -s ../config/app.conf link.conf
readlink -f link.conf
# Output: /home/user/config/app.conf  (absolute, resolved)
```

### Practical Scripting with readlink

```bash
#!/bin/bash
# Get the directory where the script itself lives, resolving symlinks
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
echo "Script directory: $SCRIPT_DIR"
```

This pattern is ubiquitous in production scripts. Without `readlink -f`, if someone runs the script via a symlink, `$0` gives the symlink path, not the real script location.

## Common Pitfalls & Gotchas

1. **Hard links and `rm`**: `rm` doesn't delete files—it unlinks directory entries. Running `rm original.txt` on our earlier example leaves `hardlink.txt` perfectly intact. The data persists until the link count hits zero. This is why `rm` and `unlink` are essentially the same syscall.

2. **Symlinks and `find`**: By default, `find` does NOT follow symlinks. If you have a symlink to `/`, `find /path -name "*.log"` won't descend into it. Use `-L` to follow, but beware of infinite loops. Always test with `-maxdepth` first.

3. **Relative symlinks break when moved**: A symlink `ln -s ../lib/libfoo.so libfoo.so` stores the *string* `../lib/libfoo.so`. If you move the symlink file to a different directory, the relative path resolves incorrectly. Absolute symlinks (`ln -s /usr/lib/libfoo.so`) don't break on move, but they break if the target moves. Choose based on your deployment model.

## Try It Yourself

1. **Hard link experiment**: Create a file, make a hard link, then `rm` the original. Verify the hard link still works. Check the link count with `stat` before and after.

2. **Symlink chain resolution**: Create a chain: `A -> B -> C -> /tmp/target`. Use `readlink` and `readlink -f` on `A`. Observe the difference. Then delete `/tmp/target` and see what `readlink -f` returns (nothing—it fails silently).

3. **Script location**: Write a small script that prints its own directory using `dirname "$0"`. Then create a symlink to the script in a different directory and run it via the symlink. Fix it using the `readlink -f` pattern above.

## Next Up

Tomorrow: **Finding Files: find, locate, which, whereis**. We'll move from linking files to finding them—mastering `find` expressions, the `locate` database, and when to use `which` vs `whereis` for locating executables and source files.
