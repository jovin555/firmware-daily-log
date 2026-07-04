---
title: "Day 22: sudo & /etc/sudoers: Privilege Escalation"
date: 2026-07-04
tags: ["til", "lfcs", "sudo", "security"]
---

## What I Explored Today

Today I dug into the mechanics of privilege escalation via `sudo` and its configuration file `/etc/sudoers`. While I've used `sudo` daily for years, I wanted to understand the exact syntax, security model, and best practices that LFCS expects. I learned how to grant granular permissions (down to specific commands and arguments), how to use `visudo` safely, and how to avoid the most common misconfigurations that leave systems vulnerable.

## The Core Concept

`sudo` (superuser do) is not just a simple "make me root" tool. It's a policy engine that controls *who* can run *what* commands, on *which* hosts, as *which* users, with *what* arguments. The `/etc/sudoers` file defines these rules, and it is parsed by `sudo` every time a command is executed.

The key insight: `sudo` operates on a **least-privilege** model. You should never grant full root access unless absolutely necessary. Instead, grant only the specific commands a user or group needs. For example, a database admin might only need `sudo systemctl restart postgresql` and `sudo -u postgres psql`, not `sudo -i` or `sudo ALL`.

The `/etc/sudoers` file uses a specific grammar. Each rule looks like:

```
user  hostname=(runas_user)  TAG: command
```

- `user`: who is allowed
- `hostname`: which machine (usually `ALL` for single-user systems)
- `runas_user`: which user they can run the command as (defaults to root if omitted)
- `TAG`: optional modifiers like `NOPASSWD`, `NOEXEC`, `SETENV`
- `command`: the full path to the command (with optional wildcards)

## Key Commands / Configuration / Code

### Editing safely with `visudo`

Never edit `/etc/sudoers` directly with a regular editor. `visudo` locks the file, checks syntax, and prevents you from saving a broken configuration that could lock you out.

```bash
# Always use visudo
sudo visudo

# To edit with a specific editor (e.g., vim)
sudo EDITOR=vim visudo

# Check syntax of an existing file without editing
sudo visudo -c
```

### Common sudoers entries

```bash
# Grant full root access to user 'alice' (use sparingly)
alice ALL=(ALL:ALL) ALL

# Grant user 'bob' permission to run any command as root, no password
bob ALL=(ALL) NOPASSWD: ALL

# Allow members of the 'wheel' group to run all commands
%wheel ALL=(ALL) ALL

# Grant user 'dbadmin' only specific commands
dbadmin ALL=(root) /usr/bin/systemctl restart postgresql, /usr/bin/systemctl status postgresql, /usr/bin/journalctl -u postgresql

# Allow user 'webdev' to run commands as user 'www-data' without password
webdev ALL=(www-data) NOPASSWD: /usr/bin/git pull, /usr/bin/systemctl reload nginx

# Use Cmnd_Alias for readability
Cmnd_Alias SHUTDOWN = /usr/sbin/shutdown, /usr/sbin/reboot, /usr/sbin/halt
operator ALL=(root) NOPASSWD: SHUTDOWN

# Restrict arguments: only allow 'apt update' and 'apt upgrade', not 'apt install'
devops ALL=(root) /usr/bin/apt update, /usr/bin/apt upgrade -y
```

### Understanding the `Defaults` directive

```bash
# Keep environment clean (recommended)
Defaults        env_reset

# Log all sudo commands
Defaults        logfile=/var/log/sudo.log

# Set a timeout (in minutes) after which sudo asks for password again
Defaults        timestamp_timeout=5

# Disable root login via sudo (use with caution)
Defaults        !root_sudo
```

### Checking what you can run

```bash
# List allowed commands for your user
sudo -l

# List allowed commands for another user
sudo -l -U alice

# Run a command as a different user
sudo -u www-data whoami
# Output: www-data

# Run a command with root's environment (simulates login)
sudo -i
```

## Common Pitfalls & Gotchas

### 1. Editing `/etc/sudoers` directly with a regular editor

This is the #1 mistake. If you make a syntax error and save, `sudo` will refuse to run *any* commands, including `sudo visudo` to fix it. You'll be locked out of root access. Always use `visudo` — it performs syntax validation before saving.

**Recovery if locked out:** Boot into single-user mode (add `init=/bin/bash` to kernel command line) or use a live USB to mount the root filesystem and fix the file manually.

### 2. Using relative paths or missing full path in commands

`sudo` requires the **full absolute path** to commands. If you write `/etc/init.d/nginx restart` but the system uses systemd, the rule won't match. Always verify paths with `which` or `type -a`.

```bash
# WRONG - path may not exist
webdev ALL=(root) /etc/init.d/nginx

# RIGHT - use the actual binary
webdev ALL=(root) /usr/sbin/nginx
```

### 3. Forgetting that `NOPASSWD` applies to the *entire* entry

If you have multiple commands in one entry and use `NOPASSWD`, it applies to all of them. To mix password-required and passwordless commands, you need separate entries.

```bash
# BAD - both commands become NOPASSWD
alice ALL=(root) NOPASSWD: /usr/bin/apt update, /usr/bin/apt upgrade

# GOOD - separate entries
alice ALL=(root) NOPASSWD: /usr/bin/apt update
alice ALL=(root) /usr/bin/apt upgrade
```

## Try It Yourself

1. **Create a restricted sudo rule:** Add a new user `deployer`, then grant them permission to run only `systemctl restart nginx` and `systemctl status nginx` as root, without a password. Verify with `sudo -l -U deployer`.

2. **Audit existing sudoers:** Run `sudo visudo -c` to check your current file for syntax errors. Then run `sudo -l` as your own user and explain every entry you see. If any entry grants `ALL`, consider whether it's necessary.

3. **Test argument restriction:** Create a rule that allows a user to run `apt update` and `apt upgrade -y` but *not* `apt install`. Try running `sudo apt install htop` as that user and observe the error message.

## Next Up: File Ownership & ACLs: setfacl, getfacl

Tomorrow I'll move beyond basic `chown` and `chmod` to explore Access Control Lists (ACLs). You'll learn how to grant permissions to multiple users and groups on the same file, how to set default ACLs for new files in a directory, and how to debug permission issues with `getfacl`. This is essential for shared development environments and multi-user servers.
