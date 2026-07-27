---
title: "Day 43: Postfix, DHCP & BIND9 Basics"
date: 2026-07-27
tags: ["til", "lfcs", "postfix", "dhcp", "dns"]
---

## What I Explored Today

Today I tackled three foundational network services that underpin almost every production Linux environment: Postfix (SMTP mail transfer), DHCP (dynamic IP assignment), and BIND9 (DNS resolution). While each service solves a different problem, they share a common architectural pattern: they all run as systemd services, read plain-text configuration files, and require careful attention to firewalls and SELinux contexts. I configured a minimal but functional mail relay, a DHCP server for a /24 subnet, and a caching-only DNS resolver — all on the same host, because in the real world you rarely get to isolate services on separate boxes.

## The Core Concept

These three services represent the "holy trinity" of network infrastructure: addressing (DHCP), naming (DNS), and messaging (SMTP). Understanding why they're grouped together in the LFCS exam is practical: you'll often deploy them on the same server in edge environments (branch offices, labs, IoT gateways). The key insight is that each service has a **choke point** — a single configuration file or directive that, if misconfigured, breaks everything downstream. For Postfix it's `myorigin` and `mydestination` (which control mail routing). For DHCP it's the `subnet` declaration (which defines the lease pool). For BIND9 it's the `options` block (which sets recursion and forwarders). Master these, and the rest is commentary.

## Key Commands / Configuration / Code

### Postfix — Minimal Mail Relay

Postfix's main config is `/etc/postfix/main.cf`. For a relay that only sends mail to a smart host (e.g., an internal SMTP gateway):

```bash
# Set the domain used in outbound mail
postconf -e "myorigin = example.com"
# Only accept mail from localhost (no open relay)
postconf -e "inet_interfaces = localhost"
# Relay all outbound mail to an internal smarthost
postconf -e "relayhost = [10.0.0.1]:25"
# Disable local delivery (we're a relay only)
postconf -e "mydestination ="
# Restart to apply
systemctl restart postfix
```

To test, use `sendmail` or `swaks`:

```bash
echo "Test email body" | mail -s "Test Subject" user@example.com
# Check the mail queue
mailq
# Force delivery attempt
postqueue -f
```

### DHCP — ISC DHCP Server

ISC DHCP is configured in `/etc/dhcp/dhcpd.conf`. A minimal subnet declaration for 192.168.1.0/24:

```bash
# /etc/dhcp/dhcpd.conf
default-lease-time 600;
max-lease-time 7200;
authoritative;  # This server is authoritative for this subnet

subnet 192.168.1.0 netmask 255.255.255.0 {
    range 192.168.1.100 192.168.1.200;
    option routers 192.168.1.1;
    option domain-name-servers 8.8.8.8, 8.8.4.4;
    option domain-name "internal.example.com";
}
```

Start and enable:

```bash
systemctl enable --now dhcpd
# Check for lease assignments
cat /var/lib/dhcpd/dhcpd.leases
```

### BIND9 — Caching-Only DNS Resolver

BIND9's main config is `/etc/bind/named.conf.options`. For a caching resolver that forwards to Cloudflare:

```bash
# /etc/bind/named.conf.options
options {
    directory "/var/cache/bind";
    recursion yes;                 # Allow recursive queries
    allow-query { any; };          # Accept queries from any client
    forwarders {
        1.1.1.1;                   # Cloudflare primary
        1.0.0.1;                   # Cloudflare secondary
    };
    forward only;                  # Don't try root hints if forwarders fail
    dnssec-validation auto;
    listen-on { any; };            # Listen on all interfaces
};
```

Validate the config and restart:

```bash
named-checkconf
systemctl restart named
# Test resolution
dig @localhost google.com
```

## Common Pitfalls & Gotchas

1. **Postfix's `mydestination` default includes the hostname.** If you leave it as the default (which includes `$myhostname`), Postfix will try to deliver mail addressed to `user@yourhostname` locally. For a relay-only server, always set `mydestination =` (empty) to avoid bounces.

2. **DHCP server won't start if the interface isn't configured with a static IP.** ISC DHCPd refuses to bind to an interface that has a dynamic IP. Ensure your serving interface has a static address in `/etc/network/interfaces` or via NetworkManager before starting the service.

3. **BIND9's `allow-query` and `allow-recursion` are separate directives.** Many engineers set `allow-query { any; };` and wonder why recursion fails. You must also set `allow-recursion { any; };` (or use the same ACL) to allow clients to perform recursive lookups. Without it, BIND9 will answer only for zones it's authoritative for.

## Try It Yourself

1. **Set up a Postfix relay that forwards all mail to a public SMTP service like SendGrid or Mailgun.** Use `relayhost = [smtp.sendgrid.net]:587` and configure SASL authentication with `smtp_sasl_auth_enable = yes`. Test with `swaks` and verify the mail arrives in your inbox.

2. **Configure ISC DHCP to assign a static lease based on MAC address.** Add a `host` declaration inside your subnet block: `host printer { hardware ethernet 00:11:22:33:44:55; fixed-address 192.168.1.50; }`. Release and renew a client's lease to confirm.

3. **Convert your BIND9 caching resolver to an authoritative-only server for a fake domain.** Create a zone file for `lab.example.com` with an A record for `server.lab.example.com` pointing to 10.0.0.10. Disable recursion and test with `dig @localhost server.lab.example.com`.

## Next Up

Tomorrow we dive into system security with SELinux and AppArmor — the mandatory access control systems that can silently block your perfectly configured services. We'll break down contexts, policies, and the dreaded "AVC denial" logs.
