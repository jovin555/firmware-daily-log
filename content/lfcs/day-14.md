---
title: "Day 14: Permissions Deep Dive: SUID, SGID, Sticky Bit"
date: 2026-06-26
tags: ["til", "lfcs", "permissions", "security"]
---

## What I Explored Today

Standard read/write/execute permissions (`rwx`) are the foundation of Linux security, but they fall short when you need temporary privilege escalation or shared workspace control. Today I dove into the three special permission bits: **SUID** (Set User ID), **SGID** (Set Group ID), and the **Sticky Bit**. These bits are not just exam trivia—they're critical for understanding why `/usr/bin/passwd` can write to `/etc/shadow` or why `/tmp` prevents you from deleting another user's file. I tested each bit on real binaries and directories, verified behavior with `stat` and `ls -la`, and traced how the kernel applies them during `execve()` and file operations.

## The Core Concept

Every process in Linux has a real UID (who you are) and an effective UID (what the kernel checks for permissions). Normally they're the same. **SUID** flips this: when a file with the SUID bit set is executed, the process's effective UID becomes the file's owner (usually `root`). This is why `passwd`—owned by root but executable by anyone—can modify the shadow file. Without SUID, you'd need `sudo` for every password change, which is impractical.

**SGID** works similarly for group ownership. On executables, it elevates the effective GID to the file's group. On directories, it's more subtle: new files and subdirectories inherit the directory's group, not the creator's primary group. This is a lifesaver for shared project directories where multiple users need consistent group ownership.

**Sticky Bit** is the simplest: on a world-writable directory, it restricts deletion so only the file owner, directory owner, or root can remove or rename files. Without it, any user could delete anyone's files in `/tmp`. The bit is visible as a `t` in the execute position for others.

The kernel applies these bits at `execve()` time (for SUID/SGID on binaries) or during `unlink()`/`rename()` (for sticky directories). They are ignored on scripts on many modern systems for security reasons—a critical nuance.

## Key Commands / Configuration / Code

### Setting and viewing special bits

```bash
# View current permissions with special bits
ls -la /usr/bin/passwd /tmp
# Output shows:
# -rwsr-xr-x 1 root root 68208 ... /usr/bin/passwd   # 's' in owner execute = SUID
# drwxrwxrwt 2 root root 4096 ... /tmp               # 't' in others execute = sticky

# Set SUID on a binary (requires root)
chmod u+s /usr/local/bin/myhelper
# Equivalent octal: 4755 (4 = SUID, 755 = rwxr-xr-x)

# Set SGID on a directory
chmod g+s /projects/team
# Octal: 2755 (2 = SGID)

# Set sticky bit on a directory
chmod +t /shared/temp
# Octal: 1777 (1 = sticky, 777 = full permissions)

# Verify with stat
stat -c "%a %A %n" /usr/bin/passwd
# Output: 4755 -rwsr-xr-x /usr/bin/passwd
```

### Practical SGID directory setup

```bash
# Create shared workspace
sudo mkdir -p /srv/devteam
sudo chown root:devteam /srv/devteam
sudo chmod 2775 /srv/devteam   # SGID + rwxrwxr-x

# Now user alice creates a file
touch /srv/devteam/alice.txt
ls -la /srv/devteam/alice.txt
# Output: -rw-rw-r-- 1 alice devteam 0 ...  # Group is devteam, not alice's primary group
```

### Finding files with special permissions

```bash
# Find all SUID binaries on the system
find / -perm -4000 -type f 2>/dev/null

# Find SGID directories
find / -perm -2000 -type d 2>/dev/null

# Find world-writable directories with sticky bit (safe temp dirs)
find / -type d -perm -1000 -perm -o+w 2>/dev/null
```

## Common Pitfalls & Gotchas

1. **SUID ignored on scripts (shebang interpreters).** Most Linux kernels ignore SUID/SGID on interpreted scripts (e.g., `.sh`, `.py`) because of race conditions and LD_PRELOAD attacks. If you need privilege escalation for a script, use a compiled wrapper binary or `sudo` rules. Don't assume `chmod u+s script.sh` works—it silently does nothing on modern systems.

2. **Sticky bit does not prevent writing.** A common misconception is that sticky bit prevents others from modifying your files. It only prevents deletion/renaming. If `/tmp/somefile` is mode 777, user Bob can still overwrite its contents (e.g., `echo "hi" > /tmp/somefile`) even if Alice owns it. For true isolation, use proper directory permissions or ACLs.

3. **Octal mode confusion.** `chmod 4755` sets SUID, but `chmod 755` clears it. If you use symbolic mode like `chmod u+s` after setting octal, it's fine. But if you later run `chmod 755 file`, you lose SUID. Always verify with `ls -la` after changes. Also, `chmod 777` on a sticky directory clears the sticky bit—you must use `chmod 1777` explicitly.

## Try It Yourself

1. **Trace SUID in action.** Run `strace -e execve passwd 2>&1 | grep execve`. Observe how the kernel sets the effective UID. Then compare with `strace -e execve whoami`. Notice the difference in privilege elevation.

2. **Create an SGID project directory.** As root, create `/srv/lab`, set group to `labusers`, and apply SGID (`chmod 2775`). Log in as two different users, create files, and verify the group inheritance. Then try `chmod g-s` and repeat—see the behavior change.

3. **Test sticky bit isolation.** As a non-root user, create a file in `/tmp` with mode `777`. Have another user try to delete it (`rm /tmp/yourfile`). Then have them overwrite its contents with a redirect (`echo "new" > /tmp/yourfile`). Confirm deletion fails but overwriting succeeds.

## Next Up

Tomorrow we shift from permissions to control flow: **Shell Scripting Basics: Loops, Conditions, Functions**. We'll write real scripts that automate permission audits, parse `ls -la` output, and conditionally apply special bits—turning today's knowledge into reusable tools.
