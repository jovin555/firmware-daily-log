---
title: "Day 19: User Accounts: useradd, usermod, userdel"
date: 2026-07-01
tags: ["til", "lfcs", "users", "accounts"]
---

## What I Explored Today

Today I dug into the three pillars of Linux user account management: `useradd`, `usermod`, and `userdel`. While these commands seem straightforward on the surface, the real engineering value lies in understanding the defaults, configuration files they touch, and the subtle flags that prevent production disasters. I spent time testing edge cases like deleting a user with running processes and modifying accounts without locking them first.

## The Core Concept

User accounts are the fundamental security boundary in Linux. Every process runs as a user, and every file belongs to a user. The `/etc/passwd` file stores the account database, `/etc/shadow` holds password hashes, and `/etc/group` maps group memberships. The `useradd`, `usermod`, and `userdel` commands are wrappers that manipulate these files safely — but only if you understand what they do under the hood.

The key insight: these commands don't just add or remove lines. They also create home directories, set up skeleton files from `/etc/skel`, assign UIDs, and manage mail spools. When you delete a user, you must decide whether to remove their home directory and mail spool, or leave them for archival. Getting this wrong can lose data or leave orphaned files consuming disk.

## Key Commands / Configuration / Code

### useradd — Creating Users

The most common mistake is using `useradd` without any flags, which relies on system defaults from `/etc/default/useradd` and `/etc/login.defs`.

```bash
# Create a user with explicit home directory and shell
sudo useradd -m -d /home/jdoe -s /bin/bash -c "John Doe" jdoe

# Set password immediately (interactive)
sudo passwd jdoe

# Create a system user (UID < 1000, no home by default)
sudo useradd --system --no-create-home -s /usr/sbin/nologin appuser

# Create user with specific UID and primary group
sudo useradd -u 1500 -g developers -G docker,sudo -m alice
```

Key flags:
- `-m` : create home directory (required for interactive users)
- `-d` : specify home directory path
- `-s` : login shell
- `-c` : GECOS comment (full name)
- `-u` : specify UID
- `-g` : primary group (must exist)
- `-G` : supplementary groups (comma-separated)
- `--system` : create system account

### usermod — Modifying Users

`usermod` is for changing existing accounts. Critical: always lock the account first if you're changing UID or home directory.

```bash
# Lock an account (prevents login)
sudo usermod -L jdoe

# Unlock an account
sudo usermod -U jdoe

# Change home directory and move contents
sudo usermod -d /newhome/jdoe -m jdoe

# Add user to supplementary groups (appends to existing)
sudo usermod -aG docker jdoe

# Change primary group
sudo usermod -g staff jdoe

# Set account expiration (YYYY-MM-DD)
sudo usermod -e 2026-12-31 contractor

# Change UID (dangerous — updates file ownership automatically)
sudo usermod -u 2000 jdoe
```

The `-a` flag with `-G` is essential — without `-a`, `-G` replaces all supplementary groups.

### userdel — Removing Users

Deletion is irreversible for the account, but data can survive.

```bash
# Remove user but keep home directory and mail spool
sudo userdel jdoe

# Remove user and their home directory + mail spool
sudo userdel -r jdoe

# Force removal even if user is logged in (use with extreme caution)
sudo userdel -f jdoe

# Remove user but keep home directory (archive scenario)
sudo userdel jdoe
sudo mv /home/jdoe /archive/jdoe_terminated
```

The `-r` flag removes `/home/jdoe` and `/var/spool/mail/jdoe`. Without it, you get orphaned files.

## Common Pitfalls & Gotchas

1. **Forgetting `-a` with `usermod -G`** — If you run `sudo usermod -G docker jdoe` without `-a`, you remove jdoe from all other supplementary groups. The user might lose access to sudo, SSH, or other critical groups. Always use `-aG` unless you intentionally want to replace group membership.

2. **Deleting a user with running processes** — `userdel` without `-f` will fail if the user has running processes. But `userdel -f` kills those processes silently. In production, first run `sudo pkill -u jdoe` or `sudo killall -u jdoe` after verifying what's running with `ps -u jdoe`.

3. **UID reuse without cleanup** — If you delete a user and create a new one with the same UID, the new user inherits ownership of all files the old user owned. This is a security risk. Always use `find / -uid OLD_UID` to reassign or remove orphaned files before creating a new user with that UID.

## Try It Yourself

1. **Create a temporary test user** with a custom home directory at `/tmp/testuser`, shell `/bin/bash`, and add them to the `users` group. Set a password, then verify you can `su` to that user. Finally, delete the user with `-r` and confirm the home directory is gone.

2. **Simulate a group membership mistake**: Create a user with sudo access. Use `usermod -G` (without `-a`) to add them to a new group. Verify they lost sudo access. Fix it by re-adding them to the sudo group with `-aG`.

3. **Archive a terminated employee**: Create a user, add some files to their home directory. Delete the user *without* `-r`. Then find all orphaned files with `find / -nouser`. Move the home directory to `/archive/`. Verify no files remain owned by the deleted UID.

## Next Up

Tomorrow I'll cover **Group Management: groupadd, gpasswd & /etc/group**. We'll look at creating administrative groups, managing group passwords, and the difference between primary and supplementary group membership in practice.
