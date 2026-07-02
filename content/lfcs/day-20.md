---
title: "Day 20: Group Management: groupadd, gpasswd & /etc/group"
date: 2026-07-02
tags: ["til", "lfcs", "groups"]
---

## What I Explored Today

Today I dug into Linux group management — the commands and files that control how users are organized into groups, how group passwords work (yes, they exist), and how the `/etc/group` file structures it all. While user management gets most of the attention, group management is equally critical for implementing least-privilege access, shared resource permissions, and administrative delegation. I focused on `groupadd`, `gpasswd`, and the `/etc/group` file format, along with the often-overlooked group password mechanism.

## The Core Concept

Groups exist to simplify permission management. Instead of setting permissions for each user individually, you create a group, assign permissions to the group, and add users to it. This is the foundation of discretionary access control (DAC) on Linux.

But groups aren't just for filesystem permissions. They also control:
- **Process group membership** — which groups a process belongs to, affecting access checks
- **Administrative delegation** — via `/etc/sudoers` and `wheel` or `sudo` groups
- **Resource limits** — `pam_limits.so` can apply limits per group
- **Authentication** — group passwords allow users to temporarily join a group without being a permanent member

The `/etc/group` file is the authoritative source for group definitions. Each line defines one group with four colon-separated fields:

```
group_name:password:GID:member_list
```

The password field is rarely used today (usually `x` or empty), but it exists for the `newgrp` command, which lets a user change their current group ID if they know the group password.

## Key Commands / Configuration / Code

### Creating Groups with `groupadd`

```bash
# Basic group creation
sudo groupadd developers

# Create with a specific GID
sudo groupadd -g 1500 qa

# Create a system group (GID < 1000, no expiry)
sudo groupadd -r sysadmin

# Verify
getent group developers
# Output: developers:x:1001:
```

The `-r` flag creates a system group, typically used by services rather than human users. System groups get GIDs from the range defined in `/etc/login.defs` (usually 100-999).

### Managing Group Membership with `gpasswd`

`gpasswd` is the Swiss Army knife for group management. It handles membership, passwords, and administrators.

```bash
# Add a user to a group
sudo gpasswd -a alice developers

# Remove a user from a group
sudo gpasswd -d alice developers

# Set a group password (for newgrp access)
sudo gpasswd developers
# Prompts for password, stored in /etc/gshadow

# Add a group administrator (can add/remove members without root)
sudo gpasswd -A bob developers

# List group members
getent group developers
# Output: developers:x:1001:alice,bob
```

The `-A` flag is powerful — it delegates group administration to non-root users. The group admin can then use `gpasswd -a` and `gpasswd -d` without `sudo`.

### The `/etc/group` File

```bash
# View the file directly
cat /etc/group

# Example entries
root:x:0:
daemon:x:1:
bin:x:2:
developers:x:1001:alice,bob
qa:x:1500:charlie
```

Field breakdown:
- **Group name**: Must be unique, alphanumeric, no colons
- **Password**: `x` means shadowed in `/etc/gshadow`; empty means no password
- **GID**: Numeric ID, should be unique
- **Member list**: Comma-separated usernames (no spaces)

### The Shadow File: `/etc/gshadow`

Group passwords are stored in `/etc/gshadow`, readable only by root:

```bash
sudo cat /etc/gshadow
# Format: group:password:administrators:members
# Example:
developers:$6$xyz...:bob:alice
```

The password hash uses the same format as `/etc/shadow`. If the password field is `!`, the group is locked (no password-based access). If empty, no password is required.

### Checking Group Membership

```bash
# Current user's groups
groups

# Specific user's groups
groups alice

# Primary group
id -gn alice

# All groups for a user
id alice
# Output: uid=1001(alice) gid=1001(alice) groups=1001(alice),1002(developers)
```

## Common Pitfalls & Gotchas

1. **Group deletion doesn't remove members** — When you delete a group with `groupdel`, users who were members still exist, but their supplementary group membership is gone. Any files owned by that GID become orphaned (showing numeric GID in `ls -l`). Always check for files owned by the group before deletion:
   ```bash
   find / -gid <GID> 2>/dev/null
   ```

2. **New group membership requires re-login** — When you add a user to a group with `gpasswd -a`, the change takes effect immediately in `/etc/group`, but the user's existing processes still have the old group set. They must log out and back in (or use `newgrp` or `sg`) to pick up the new group. This is a common source of "I added them, why can't they access the file?" confusion.

3. **GID conflicts with existing files** — If you create a group with a GID that matches an existing file's numeric GID (from a deleted group), the new group automatically owns those files. This can accidentally grant access to sensitive data. Always check for orphaned GIDs before reusing them.

## Try It Yourself

1. **Create a shared project group**: Create a group called `project_x` with GID 2000. Add two users to it. Create a directory `/srv/project_x` owned by `root:project_x` with permissions `2775` (setgid + rwxrwxr-x). Verify that both users can create files in it and that new files inherit the group.

2. **Delegate group administration**: Create a group `deploy` and use `gpasswd -A` to make a non-root user the group administrator. As that user, add another member to the group without using `sudo`. Verify the membership change in `/etc/group`.

3. **Explore group passwords**: Set a group password on a test group using `gpasswd`. Use `newgrp` to switch to that group (enter the password when prompted). Check your current group with `id`. Then exit the subshell and verify your group is back to normal.

## Next Up

Tomorrow I'm tackling password management and PAM — the `passwd` and `chage` commands, the `/etc/shadow` file format, and how Pluggable Authentication Modules control everything from password complexity to account expiration. If you've ever wondered why `chage -l` shows "Password expires: never" or how to force a password change on first login, that's tomorrow's deep dive.
