---
title: "Day 08: Insecure Network Services & Weak Default Credentials"
date: 2026-07-08
tags: ["til", "threat-modeling", "default-creds", "network-services"]
---

## What I Explored Today

Today I dug into one of the most embarrassing yet persistent attack surfaces in embedded systems: insecure network services running with default credentials. I reviewed real-world CVEs—from IP cameras to industrial PLCs—where devices shipped with `root:root` SSH access or a web interface listening on all interfaces with no authentication. The pattern is depressingly common: a developer enables a debug service (Telnet, FTP, or a custom RPC endpoint) for manufacturing, forgets to disable it, and the firmware goes to production. Combine that with hardcoded credentials in the source code, and you have a remote code execution vulnerability waiting for a Shodan scan.

## The Core Concept

The root cause isn't laziness—it's a failure to treat the network service surface as a threat boundary. In embedded systems, every listening port is a potential entry point. The "why" behind this is architectural: embedded devices often run a monolithic firmware image where the network stack, application logic, and credential store live in the same unprotected memory space. Unlike a cloud server where you can rotate secrets, an embedded device's default credentials are baked into flash. If an attacker can reach port 23 or 22 with the factory password, they own the device.

The real danger is the combination of two mistakes: (1) enabling unnecessary network services (e.g., leaving `telnetd` enabled for field debugging) and (2) using weak or hardcoded credentials that never expire. Attackers automate scanning for these patterns. A single open port with `admin:admin` is a backdoor that bypasses all other security controls.

## Key Commands / Configuration / Code

### 1. Scanning for Insecure Services (Nmap)

```bash
# Scan for common embedded services on a target subnet
nmap -sV -p 23,21,22,80,443,8080,161,502 192.168.1.0/24

# -sV: version detection to identify service banners
# -p: specific ports; embedded devices often use non-standard ports
# Look for "Telnet", "FTP", "HTTP" without SSL
```

### 2. Testing Default Credentials (Hydra)

```bash
# Brute-force SSH with common default creds
hydra -l root -P /usr/share/wordlists/default-creds.txt ssh://192.168.1.100

# For HTTP basic auth on a web interface
hydra -l admin -P /usr/share/wordlists/default-creds.txt http-get://192.168.1.100/login

# Common embedded defaults: root:root, admin:admin, user:1234, support:support
```

### 3. Disabling Unnecessary Services (BusyBox / init script)

```bash
# In a BusyBox-based firmware, check /etc/inittab for telnet
# Comment out or remove the telnetd line:
# ::respawn:/usr/sbin/telnetd -l /bin/login

# Disable FTP (often vsftpd or busybox ftpd)
# Remove from /etc/init.d/rcS or systemd equivalent
# Verify with:
netstat -tlnp | grep -E ':(23|21|69)'
```

### 4. Secure Default Credential Generation (C example)

```c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

// NEVER hardcode credentials. Generate on first boot.
void generate_device_credentials(char *username, size_t uname_len,
                                  char *password, size_t pwd_len) {
    // Use device-specific entropy: MAC address + RTC
    srand(time(NULL) ^ (get_mac_address() & 0xFFFF));

    const char *chars = "abcdefghijklmnopqrstuvwxyz0123456789";
    // Generate username: "device_" + 4 random chars
    snprintf(username, uname_len, "device_");
    for (int i = 0; i < 4; i++) {
        username[7 + i] = chars[rand() % 36];
    }
    username[11] = '\0';

    // Generate password: 12 random alphanumeric chars
    for (int i = 0; i < 12; i++) {
        password[i] = chars[rand() % 36];
    }
    password[12] = '\0';

    // Store in secure flash partition (not shown)
    // Print once to serial console for first-time setup
    printf("Device credentials:\nUsername: %s\nPassword: %s\n", username, password);
}
```

### 5. Minimal Secure Network Service (Python example for testing)

```python
import socket
import hashlib
import os

# Never use plaintext passwords; use challenge-response
SECRET_KEY = os.urandom(32)  # Generated at boot, stored in TPM if available

def handle_client(conn):
    # Send random challenge
    challenge = os.urandom(16)
    conn.send(challenge)
    
    # Receive HMAC response
    response = conn.recv(32)
    expected = hmac.new(SECRET_KEY, challenge, hashlib.sha256).digest()
    
    if response == expected:
        conn.send(b"Authenticated\n")
        # ... handle commands
    else:
        conn.send(b"Auth failed\n")
        conn.close()

# Bind only to internal interface, not 0.0.0.0
server = socket.socket()
server.bind(('127.0.0.1', 9999))  # Only localhost!
server.listen()
```

## Common Pitfalls & Gotchas

1. **Binding to `0.0.0.0` instead of a specific interface.** Many embedded developers use `INADDR_ANY` (0.0.0.0) for convenience, which exposes the service on all network interfaces—including Wi-Fi, Ethernet, and even cellular modems. Always bind to the management interface IP or `127.0.0.1` for local-only services.

2. **Hardcoding credentials in a separate "config" file that ships with firmware.** I've seen teams move credentials from source code to a JSON config file, thinking that's secure. It's not—the config is still in the flash image. An attacker can extract it with `binwalk` or a JTAG probe. Credentials must be unique per device, generated at first boot, and stored in a one-time-programmable region.

3. **Leaving debug services enabled in production builds.** The classic mistake: a `#ifdef DEBUG` block that enables Telnet or a raw UART-to-TCP bridge. When the release build is cut, the preprocessor flag is accidentally left defined. Always have a CI check that greps for `telnetd`, `ftpd`, and raw socket servers in the final binary.

## Try It Yourself

1. **Scan your own development board.** Connect a Raspberry Pi or ESP32 to your network and run `nmap -sV -p 1-65535 <device_ip>`. Identify every open port. For each one, determine: is this service necessary? Does it require authentication? Is it bound to all interfaces?

2. **Extract and audit firmware.** Download a firmware image for a common IoT device (check your local laws). Use `binwalk -e firmware.bin` to extract the filesystem. Grep for strings like "password", "admin", "root", and look for hardcoded credentials in binaries or config files.

3. **Implement a first-boot credential generator.** Write a C or Python function that generates unique credentials using device-specific entropy (MAC address, serial number, or RTC). Ensure the credentials are printed once to a serial console and never stored in the firmware image. Test that two devices with the same firmware get different credentials.

## Next Up

Tomorrow we dive into **Buffer Overflows in C: Stack Smashing & Mitigations**. We'll walk through a real stack overflow, examine the crash dump, and implement stack canaries and ASLR bypasses. Bring your GDB skills.
