---
title: "Day 18: IEC 62443: Industrial Cybersecurity & Safety Convergence"
date: 2026-06-30
tags: ["til", "cfse", "iec62443", "cybersecurity"]
---

## What I Explored Today

Today I dug into IEC 62443, the international standard for industrial communication network security, and its critical intersection with functional safety (IEC 61508 / IEC 61511). While safety engineering has traditionally focused on preventing random hardware failures and systematic faults, the modern industrial control system (ICS) environment demands that we also consider intentional, malicious acts. A safety function is only as reliable as the network it rides on — if an attacker can disable a safety PLC or spoof a sensor reading, the safety case collapses. I spent the afternoon mapping the IEC 62443 security levels (SL 1–4) against Safety Integrity Levels (SIL 1–4) and testing practical defense-in-depth configurations on a simulated Modbus/TCP safety network.

## The Core Concept

The fundamental insight of IEC 62443 is that **security and safety are not orthogonal** — they share a common goal: preventing harm. A safety system that is insecure is, by definition, unsafe. The standard introduces the concept of a **Security Level (SL)** , analogous to SIL, which measures the capability of a system to resist cyber attacks. SL 1 protects against casual or coincidental violation; SL 4 protects against intentional, sophisticated attacks using advanced resources.

The convergence happens in the **Safety Instrumented System (SIS)** design. Consider a gas burner safety shutdown: the SIL-rated logic solver must receive a valid flame signal. If an attacker injects a false "flame present" message, the safety function is defeated. IEC 62443 mandates **defense-in-depth** — network segmentation, secure communication channels, and integrity checks — to ensure the safety function's integrity is preserved even under cyber attack. The key takeaway: you cannot claim SIL compliance without addressing the security of the communication path. This is explicitly called out in IEC 61511-1 (2016) Clause 8.2.2, which requires that security risks be identified and mitigated.

## Key Commands / Configuration / Code

Below is a practical example of configuring a **Modbus/TCP security gateway** using `iptables` on a Linux-based edge controller to enforce IEC 62443 SL-2 zone separation. This isolates the safety PLC (Zone A) from the corporate IT network (Zone B).

```bash
# Flush existing rules and set default policies
iptables -F
iptables -P INPUT DROP
iptables -P FORWARD DROP
iptables -P OUTPUT ACCEPT

# Allow established connections (stateful inspection)
iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT

# Allow local loopback
iptables -A INPUT -i lo -j ACCEPT

# Zone A: Safety PLC subnet (192.168.10.0/24)
# Only allow Modbus/TCP (port 502) from safety HMI (192.168.10.10)
iptables -A INPUT -s 192.168.10.10 -d 192.168.10.0/24 -p tcp --dport 502 -j ACCEPT

# Zone B: Corporate IT (10.0.0.0/8) — BLOCK all Modbus/TCP
iptables -A INPUT -s 10.0.0.0/8 -p tcp --dport 502 -j DROP

# Log dropped packets for security audit (IEC 62443-3-3 SR 6.2)
iptables -A INPUT -j LOG --log-prefix "SECURITY_DROP: " --log-level 4

# Save rules persistently
iptables-save > /etc/iptables/rules.v4
```

**Explanation:** This rule set enforces a **conduit** between zones. Only the safety HMI can initiate Modbus/TCP connections to the safety PLC. All other traffic — especially from the corporate network — is dropped and logged. This directly satisfies IEC 62443-3-3 Requirement SR 5.1 (Zone segmentation) and SR 6.2 (Audit log).

For **integrity verification** of safety messages, consider adding a CRC-32 check in the application layer:

```c
// Pseudo-code for safety message integrity (IEC 62443-4-2 CR 3.1)
uint32_t calculate_crc32(uint8_t *data, size_t len) {
    uint32_t crc = 0xFFFFFFFF;
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int j = 0; j < 8; j++) {
            crc = (crc >> 1) ^ (crc & 1 ? 0xEDB88320 : 0);
        }
    }
    return ~crc;
}

// On receive: verify CRC before processing safety command
if (received_crc != calculate_crc32(payload, payload_len)) {
    // Reject message, log security event, trigger safe state
    safety_actuator_set(SHUTDOWN);
    syslog(LOG_AUTH | LOG_WARNING, "CRC mismatch on safety message from %s", src_ip);
}
```

## Common Pitfalls & Gotchas

1. **Assuming security is only an IT problem.** I’ve seen safety engineers hand off the network design to IT, who then apply standard enterprise patches without understanding safety timing constraints. A Windows Update that reboots a safety HMI mid-cycle is a safety hazard. Always maintain a **safety-secure change management process** (IEC 62443-2-4).

2. **Overlooking the human interface.** Many SIS have local maintenance panels with no authentication. An attacker with physical access can bypass all network security. IEC 62443-4-2 requires **CR 1.1** (human user identification and authentication) even on local engineering ports. Use a hardware key or biometric reader on the safety panel.

3. **Confusing SL with SIL.** They are not equivalent. A system can be SIL 3 capable but only SL 1 secure. If the threat environment requires SL 2, your safety case is invalid. Always perform a **cyber threat risk assessment** (IEC 62443-3-2) in parallel with the SIL determination.

## Try It Yourself

1. **Map your current SIS network.** Draw a zone diagram (like IEC 62443-3-3 Figure 1). Identify every conduit between safety and non-safety zones. For each conduit, list the protocol (Modbus/TCP, OPC UA, PROFINET) and ask: “What happens if this message is spoofed or delayed?”

2. **Implement the iptables rules above** on a test Linux gateway between a safety PLC simulator (e.g., OpenPLC) and a corporate network VM. Use `nmap` from the corporate side to verify that port 502 is filtered. Then try a Modbus write from an unauthorized IP — confirm the packet is logged in `/var/log/syslog`.

3. **Add a CRC-32 integrity check** to a safety function in your preferred language (C, Python, or ladder logic). Simulate a corrupted message (flip one bit) and verify the function enters a safe state (e.g., outputs de-energized). Measure the timing overhead — ensure it stays within the safety response time (PFD/PFH budget).

## Next Up

Tomorrow we pivot to exam mode: **CFSE Exam Prep: Key Topics, Structure & Mock Questions**. I’ll break down the CFSE exam blueprint, highlight the highest-weight domains, and walk through five realistic multiple-choice questions with detailed explanations. If you’re targeting the Certified Functional Safety Expert credential, don’t miss it.

---
*This post is part of a daily engineering log. All configurations should be tested in a non-production environment before deployment.*
