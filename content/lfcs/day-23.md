---
title: "Day 23: File Ownership & ACLs: setfacl, getfacl"
date: 2026-07-05
tags: ["til", "lfcs", "acl", "permissions"]
---

## What I Explored Today

Standard Unix permissions (owner/group/other) break down fast in real-world multi-user systems. Today I dug into Access Control Lists (ACLs) — the mechanism that lets you grant permissions to arbitrary users and groups beyond the traditional three-role model. I worked through `getfacl` and `setfacl` to inspect and modify ACLs, and I confirmed how ACLs interact with the classic permission bits. This is essential for shared project directories, CI/CD runners, and any environment where "one group fits all" isn't enough.

## The Core Concept

The traditional permission model gives you exactly three slots: owner, group, and other. That works for a single user and a single group, but what happens when you need to give read access to user `alice`, write access to user `bob`, and deny access to user `mallory` — all on the same file? You can't do it with `chmod` alone.

ACLs solve this by attaching an ordered list of Access Control Entries (ACEs) to each file or directory. Each ACE specifies a principal (user or group) and a set of permissions. The kernel checks these entries in order when a process tries to access a file. If no explicit ACE matches, the fallback is the "other" mask.

There are two types of ACLs:
- **Access ACLs** — control access to the file or directory itself.
- **Default ACLs** — only apply to directories; new files and subdirectories created inside inherit these permissions automatically.

The key insight: when you set an ACL, the traditional permission bits become a mask. The "group" class in `ls -l` no longer shows the owning group's permissions — it shows the ACL mask, which limits the maximum permissions any named user or group can have. This catches many engineers off guard.

## Key Commands / Configuration / Code

### Inspecting ACLs with `getfacl`

```bash
# Show ACL on a file
getfacl /var/log/app.log

# Output:
# file: /var/log/app.log
# owner: root
# group: adm
# user::rw-
# group::r--
# mask::r--
# other::r--
```

The `mask` entry is critical. It caps the effective permissions for all named users and groups. If the mask is `r--`, even if you grant `alice` write access, she'll only get read.

### Setting ACLs with `setfacl`

```bash
# Grant user alice read and write access
setfacl -m u:alice:rw /shared/project

# Grant group devs read, write, and execute
setfacl -m g:devs:rwx /shared/project

# Remove a specific user entry
setfacl -x u:alice /shared/project

# Remove all ACL entries (revert to standard permissions)
setfacl -b /shared/project
```

### Default ACLs for directories

```bash
# Set default ACL so new files get rw for alice, r for devs
setfacl -d -m u:alice:rw /shared/project
setfacl -d -m g:devs:rx /shared/project

# Verify inheritance
getfacl /shared/project
# Output includes:
# default:user:alice:rw-
# default:group:devs:r-x
```

### Recursive ACL application

```bash
# Apply ACL to existing files and directories recursively
# -R for recursive, --mask to recalculate mask entries
setfacl -R -m u:alice:rw /shared/project

# Preserve existing ACLs while adding new ones (no overwrite)
setfacl -R -m u:bob:rx /shared/project
```

### Checking effective permissions

```bash
# Show ACL with effective rights column
getfacl -e /shared/project/file.txt
# Output:
# user:alice:rw-                 # effective: r--
# group:devs:r-x                 # effective: r--
# mask::r--
```

The `-e` flag reveals the mask's impact. In this example, alice and devs both have their permissions capped by the mask.

## Common Pitfalls & Gotchas

### 1. The mask silently limits permissions

This is the #1 trap. You set `setfacl -m u:alice:rwx file`, but `ls -l` shows `rw-r-----`. The mask (shown in the group field) is `r--`, so alice only gets read. Always check the mask after setting ACLs. Use `setfacl -m m::rwx` to raise the mask if needed.

### 2. `chmod` resets the ACL mask

Running `chmod 755 file` after setting ACLs recalculates the mask based on the group permissions. If the group was `r--`, the mask becomes `r--`, and your carefully crafted user ACLs get neutered. Always use `setfacl` to modify permissions on files with ACLs, or re-apply ACLs after `chmod`.

### 3. Default ACLs don't apply to existing files

Setting a default ACL on a directory only affects *new* files and subdirectories created inside it. Existing files keep their current ACLs. You must run `setfacl -R` explicitly to propagate the ACL to existing content.

### 4. ACLs and backup/restore

`tar` with `--acls` preserves ACLs, but `cp` does not by default. Use `cp -a` (archive mode) or `rsync -A` to copy ACLs. If you forget, you'll silently lose all your fine-grained permissions.

## Try It Yourself

1. **Shared project directory with mixed access**  
   Create `/srv/team-project`. Set the owner to `root`, group to `developers`. Grant user `alice` full access (rwx), user `bob` read-only (r-x), and group `interns` no access (---). Verify with `getfacl` and test by switching users.

2. **Default ACL inheritance test**  
   On the same directory, set a default ACL giving `alice` rwx and `bob` r-x. Create a new file and a new subdirectory inside. Run `getfacl` on both to confirm inheritance. Then create a file with `umask 077` — does the ACL still apply?

3. **Mask manipulation experiment**  
   Set a file ACL with `u:alice:rwx`. Check the mask. Now run `chmod 640 file`. Re-check the ACL and test alice's effective permissions. Fix it by adjusting the mask with `setfacl -m m::rwx`.

## Next Up

Tomorrow I'm diving into the Linux boot process — from BIOS/UEFI through GRUB to the kernel handoff. Understanding the boot sequence is critical for troubleshooting boot failures, customizing initramfs, and configuring kernel parameters. We'll trace the exact path from power-on to login prompt.
