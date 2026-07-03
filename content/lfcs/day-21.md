---
title: "Day 21: Passwords & PAM: passwd, chage, /etc/shadow"
date: 2026-07-03
tags: ["til", "lfcs", "passwords", "pam"]
---

## What I Explored Today

Today I dug into the Linux authentication stack: how passwords are stored, aged, and validated. I already knew `/etc/shadow` existed, but I hadn't fully appreciated how `passwd`, `chage`, and PAM (Pluggable Authentication Modules) work together to enforce password policies. This isn't just about changing a password—it's about understanding the entire lifecycle of a credential on a Linux system, from hashing to aging to lockout.

## The Core Concept

Passwords are the most common authentication factor on Linux, but they're never stored in plaintext. The `/etc/shadow` file contains the salted, hashed password, along with aging metadata that controls when a user must change it. The `passwd` command writes to this file, and `chage` reads and modifies the aging fields.

But the real magic happens through PAM. When you run `passwd`, it doesn't directly write to `/etc/shadow`. Instead, it calls PAM modules like `pam_unix.so` and `pam_cracklib.so` (or `pam_pwquality.so` on modern systems). These modules enforce password complexity, history, and hashing algorithms. PAM is the policy engine; `passwd` and `chage` are just the user-facing tools.

The `/etc/shadow` format is colon-delimited with nine fields:
1. Username
2. Hashed password (or `!`/`*` for locked accounts)
3. Last password change (days since epoch)
4. Minimum days between changes
5. Maximum days before forced change
6. Warning days before expiration
7. Inactive days after expiration before lock
8. Account expiration date (days since epoch)
9. Reserved

Understanding this structure is critical for troubleshooting login issues and automating user management.

## Key Commands / Configuration / Code

### Inspecting `/etc/shadow`
```bash
# View shadow entry for a user (requires root)
sudo grep jdoe /etc/shadow
# Output: jdoe:$y$j9T$...:19876:0:90:7:30:20000:

# Field breakdown:
# $y$ = yescrypt hash (default on modern systems)
# 19876 = last changed June 15, 2024
# 0 = no minimum days
# 90 = password expires after 90 days
# 7 = warn 7 days before expiry
# 30 = account locked 30 days after expiry
# 20000 = account expires Oct 5, 2024
```

### Changing passwords with `passwd`
```bash
# Interactive password change for current user
passwd

# Root can change any user's password
sudo passwd jdoe

# Force password change on next login (sets lastchange to 0)
sudo passwd -e jdoe

# Lock and unlock accounts
sudo passwd -l jdoe   # Prepend ! to hash, disabling login
sudo passwd -u jdoe   # Remove ! to re-enable

# Check password status
sudo passwd -S jdoe
# Output: jdoe P 06/15/2024 0 90 7 30
# P = usable password, L = locked, NP = no password
```

### Managing password aging with `chage`
```bash
# View aging information
sudo chage -l jdoe
# Output:
# Last password change : Jun 15, 2024
# Password expires     : Sep 13, 2024
# Password inactive    : Oct 13, 2024
# Account expires      : Oct 05, 2024
# Minimum number of days between password change : 0
# Maximum number of days between password change : 90
# Number of days of warning before password expires : 7

# Set maximum password age to 60 days
sudo chage -M 60 jdoe

# Force password change on next login
sudo chage -d 0 jdoe

# Set account to never expire
sudo chage -E -1 jdoe

# Set warning to 14 days before expiry
sudo chage -W 14 jdoe
```

### PAM configuration for password quality
```bash
# View password quality rules (RHEL/CentOS/Fedora)
cat /etc/security/pwquality.conf
# Typical settings:
# minlen = 12
# dcredit = -1   # require at least 1 digit
# ucredit = -1   # require at least 1 uppercase
# lcredit = -1   # require at least 1 lowercase
# ocredit = -1   # require at least 1 special char

# The PAM stack that enforces this (on authselect systems)
cat /etc/pam.d/system-auth | grep password
# password    requisite     pam_pwquality.so try_first_pass local_users_only retry=3
# password    sufficient    pam_unix.so sha512 shadow nullok try_first_pass use_authtok
```

### Manually editing `/etc/shadow` (dangerous but sometimes necessary)
```bash
# Remove password hash to disable password auth (not lock)
# Change: jdoe:$y$...:19876:...  →  jdoe:*:19876:...
# * means no password auth possible

# Set account to expire immediately
# Change last field from empty to 0
# jdoe:$y$...:19876:0:90:7:30:0
```

## Common Pitfalls & Gotchas

1. **`passwd -l` vs removing the hash**: Locking with `passwd -l` prepends `!` to the hash, making it unparseable. This is reversible with `passwd -u`. Manually replacing the hash with `*` or `!` is permanent unless you restore the original hash. Always use `passwd -l`/`-u` for operational lockouts.

2. **`chage -d 0` forces immediate password change**: This sets the last change date to epoch (0). The user *must* change password on next login. However, if `minlen` or other PAM constraints are too strict, the user may get stuck in a loop where they can't set a compliant password. Always test password policies before mass-forcing changes.

3. **Shadow file corruption**: Editing `/etc/shadow` manually with a text editor can corrupt the file if you mistype a field or introduce a bad hash. Always use `vipw -s` (which locks the file and runs syntax checks) instead of a raw editor. A corrupted shadow file can lock out all users, including root.

## Try It Yourself

1. **Audit password aging for all users**: Write a one-liner that lists every user with a password hash in `/etc/shadow`, showing their username, last change date, and max age. Hint: use `awk` to filter out lines with `*` or `!` in the second field, then pipe to `chage -l` or parse the shadow fields directly.

2. **Simulate a forced password reset**: Create a test user, set a password, then use `chage -d 0` to force a change on next login. Log in as that user and observe the password change prompt. Verify the shadow file before and after.

3. **Lock and unlock a user account**: Use `passwd -l` to lock a test account, then attempt to `su` to that user. Verify the shadow entry shows `!` prepended. Unlock with `passwd -u` and confirm the `!` is removed and login works again.

## Next Up

Tomorrow: **sudo & /etc/sudoers: Privilege Escalation** — we'll break down the sudoers file syntax, understand privilege escalation rules, and learn how to grant granular permissions without giving away the root password.
