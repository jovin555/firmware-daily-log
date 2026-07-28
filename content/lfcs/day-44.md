---
title: "Day 44: System Security: SELinux & AppArmor"
date: 2026-07-28
tags: ["til", "lfcs", "selinux", "security"]
---

## What I Explored Today

Today I dug into the two dominant Linux Mandatory Access Control (MAC) systems: SELinux (primarily on RHEL/CentOS/Fedora) and AppArmor (primarily on Ubuntu/Debian/SUSE). While discretionary access control (DAC) via `chmod`/`chown` is the first line of defense, MAC systems enforce policies that even the root user cannot override without explicit rule changes. I spent the day learning how to check statuses, interpret denials, toggle enforcement modes, and apply basic policy adjustments—skills that are essential for any production Linux engineer.

## The Core Concept

Standard Linux permissions (owner/group/other, read/write/execute) are discretionary: if a process runs as root, it can do anything. That's a single point of failure. SELinux and AppArmor add a second layer: they define what a *process* (not just a user) is allowed to do. For example, even if the Apache HTTPD process runs as `www-data`, SELinux can prevent it from reading `/etc/shadow` or writing to `/var/www/html` if the file's security context doesn't match the expected type.

**Why this matters in practice:**  
- A compromised web server process can't escalate to full system compromise if the MAC policy restricts its capabilities.  
- Many LFCS exam scenarios involve a service failing silently because SELinux is blocking an action—no error in the application logs, only in the audit log.  
- You must know how to diagnose and fix these issues without disabling the entire MAC system (which is a common but dangerous reflex).

The key difference between SELinux and AppArmor: SELinux uses file *contexts* (labels like `httpd_sys_content_t`) and a centralized policy, while AppArmor uses *path-based profiles* (e.g., `/usr/sbin/httpd` has a profile that lists allowed file paths and capabilities). Both achieve the same goal but with different tooling.

## Key Commands / Configuration / Code

### SELinux (RHEL/CentOS/Fedora)

```bash
# Check current mode (Enforcing, Permissive, Disabled)
getenforce
# Output: Enforcing

# Temporarily set permissive mode (for debugging)
sudo setenforce 0

# Check SELinux status and policy details
sestatus
# Output includes: Loaded policy name, Current mode, Policy MLS status

# Find the security context of a file
ls -Z /var/www/html/index.html
# Output: system_u:object_r:httpd_sys_content_t:s0 /var/www/html/index.html

# Find the context of a running process
ps -eZ | grep httpd
# Output: system_u:system_r:httpd_t:s0  12345 ? 00:00:00 httpd

# Change file context (restore to default)
sudo restorecon -Rv /var/www/html/

# Manually set context (use with caution)
sudo chcon -t httpd_sys_content_t /var/www/html/custom_dir

# Search audit log for SELinux denials
sudo ausearch -m avc -ts recent
# Or use sealert for human-readable explanations
sudo sealert -a /var/log/audit/audit.log

# List all SELinux booleans (toggles for common features)
getsebool -a | grep httpd
# Example: httpd_enable_homedirs --> on

# Set a boolean persistently
sudo setsebool -P httpd_enable_homedirs on
```

### AppArmor (Ubuntu/Debian)

```bash
# Check status
sudo aa-status
# Shows loaded profiles, modes (enforce/complain), and processes

# List profiles
sudo aa-status | grep "profiles are loaded"

# Set a profile to complain mode (log violations but don't block)
sudo aa-complain /usr/sbin/nginx

# Set back to enforce mode
sudo aa-enforce /usr/sbin/nginx

# View AppArmor denials in syslog
sudo journalctl -u apparmor | grep DENIED
# Or check /var/log/syslog
grep "apparmor=" /var/log/syslog

# Generate a new profile based on application logs
sudo aa-genprof /usr/sbin/nginx
# Follow interactive prompts to allow/deny actions

# Manually edit a profile (e.g., /etc/apparmor.d/usr.sbin.nginx)
sudo vim /etc/apparmor.d/usr.sbin.nginx
# Then reload
sudo apparmor_parser -r /etc/apparmor.d/usr.sbin.nginx
```

## Common Pitfalls & Gotchas

1. **Disabling SELinux instead of fixing it**  
   Setting `SELINUX=disabled` in `/etc/selinux/config` requires a reboot and leaves the system unprotected. The correct approach: use `setenforce 0` temporarily, then fix the context or boolean, then `setenforce 1`. Never run production with SELinux disabled.

2. **Confusing `chcon` with `restorecon`**  
   `chcon` manually sets a context but does not survive a file system relabel. `restorecon` sets the context based on policy defaults. Always prefer `restorecon` unless you're creating a custom policy.

3. **AppArmor profile syntax errors**  
   A single typo in an AppArmor profile can cause the service to fail silently. Always test with `aa-complain` first, then switch to enforce after verifying the logs show no unexpected denials.

4. **SELinux booleans vs. file contexts**  
   If a service can't access a file, check the file's context first. If the context is correct, check if a boolean needs to be enabled (e.g., `httpd_enable_homedirs` for user directories).

## Try It Yourself

1. **SELinux: Diagnose a blocked service**  
   On a RHEL system, install `httpd` and try to serve a file from `/root/secret.html`. Use `ausearch -m avc -ts recent` to find the denial, then fix it by moving the file to `/var/www/html/` and running `restorecon -Rv /var/www/html/`.

2. **AppArmor: Create a custom profile**  
   On Ubuntu, install `nginx`. Use `aa-genprof /usr/sbin/nginx` to generate a profile. Start nginx, then use `aa-logprof` to review and approve denials. Switch the profile to enforce mode and verify the service still works.

3. **Toggle enforcement modes**  
   For both SELinux and AppArmor, practice switching between enforcing and permissive/complain modes. Verify the mode change with `getenforce` or `aa-status`. Then revert to enforcing and confirm the system is protected.

## Next Up

Day 45: **Full Mock Exam — All Domains**. We'll combine everything from the past 44 days into a comprehensive practice exam covering system startup, storage, networking, package management, service configuration, and security. Bring your terminal and your patience.
