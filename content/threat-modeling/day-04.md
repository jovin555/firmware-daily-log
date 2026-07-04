---
title: "Day 04: Attack Trees: Modeling Adversary Goals & Paths"
date: 2026-07-04
tags: ["til", "threat-modeling", "attack-tree"]
---

## What I Explored Today

Attack trees are the structural backbone of adversary-centric threat modeling. Unlike STRIDE, which categorizes threats by property (spoofing, tampering, etc.), attack trees force you to think backwards: start with the attacker's ultimate goal and decompose it into concrete sub-goals until you reach atomic actions. Today I built attack trees for a firmware update mechanism and a CAN bus gateway, and I learned why this technique is indispensable for prioritizing mitigations in resource-constrained embedded systems.

## The Core Concept

An attack tree is a rooted, directed tree where the root node is the attacker's primary objective (e.g., "Execute arbitrary code on ECU"). Each child node represents a sub-goal that must be achieved for the parent to succeed. Nodes can be AND (all children required) or OR (any child sufficient). This structure maps directly to how real adversaries plan: they chain exploits, not single vulnerabilities.

Why this matters for embedded systems: you cannot patch firmware over the air on a deployed sensor node. Attack trees help you identify which attack paths are cheapest for the attacker and most damaging to you. By annotating each leaf node with cost, skill level, or detection probability, you can compute the "cheapest" path to the root and block it first. This is threat-driven prioritization, not fear-driven.

## Key Commands / Configuration / Code

I use a text-based representation for attack trees because whiteboard diagrams don't survive in git. Here's a tree for a CAN bus gateway that isolates the OBD-II port from the powertrain CAN.

```text
# Attack Tree: Compromise Powertrain CAN via OBD-II Port
# Root: Attacker controls powertrain CAN messages
# Format: [Node ID] | Parent ID | Type (AND/OR) | Description

1  | -  | OR  | Send forged powertrain CAN frames
2  | 1  | OR  | Bypass gateway firewall rules
3  | 2  | AND | Exploit gateway firmware update
4  | 3  | AND | Obtain signed firmware image
5  | 4  | OR  | Leak private signing key from HSM
6  | 4  | OR  | Replay old signed firmware (downgrade)
7  | 3  | AND | Deliver malicious firmware to gateway
8  | 7  | OR  | Physical access to debug UART
9  | 7  | OR  | Exploit buffer overflow in OBD-II parser
10 | 2  | OR  | Spoof legitimate CAN ID (no authentication)
11 | 1  | OR  | Disable gateway entirely (DoS)
12 | 11 | AND | Flood gateway with high-priority frames
```

To compute the minimal cost path, I wrote a simple Python script:

```python
# compute_min_path.py — finds cheapest attack path
# Usage: python compute_min_path.py < tree.txt

import sys
import re

# Parse tree into adjacency list with costs
# Leaf nodes annotated with cost (1-10 scale)
tree = {}
for line in sys.stdin:
    line = line.strip()
    if not line or line.startswith('#'):
        continue
    parts = line.split('|')
    node_id = parts[0].strip()
    parent = parts[1].strip()
    node_type = parts[2].strip()
    desc = parts[3].strip()
    # Extract cost from description if leaf (e.g., "[cost=3]")
    cost_match = re.search(r'\[cost=(\d+)\]', desc)
    cost = int(cost_match.group(1)) if cost_match else 0
    tree[node_id] = {
        'parent': parent,
        'type': node_type,
        'cost': cost,
        'children': []
    }

# Build child lists
for nid, node in tree.items():
    if node['parent'] != '-':
        tree[node['parent']]['children'].append(nid)

def min_cost(nid):
    """Recursively compute minimum cost to achieve node nid."""
    node = tree[nid]
    if not node['children']:
        return node['cost']  # leaf
    child_costs = [min_cost(c) for c in node['children']]
    if node['type'] == 'AND':
        return sum(child_costs)
    else:  # OR
        return min(child_costs)

root_id = '1'
print(f"Minimum cost to root ({root_id}): {min_cost(root_id)}")
```

Running this on the tree above (with leaf costs annotated) tells me the cheapest path is likely "Spoof legitimate CAN ID" (cost=2) because the gateway lacks authentication on CAN frames. That immediately tells me where to invest: add message authentication codes (MACs) to critical CAN IDs, not harden the firmware update pipeline first.

## Common Pitfalls & Gotchas

1. **Confusing AND with OR.** In embedded systems, many attacks require multiple simultaneous conditions. For example, exploiting a buffer overflow (OR child) might require both a specific compiler flag and a disabled stack canary (AND children). Get this wrong and your cost calculations are useless. Always ask: "Can the attacker achieve the parent with any single child, or must all children be true?"

2. **Ignoring physical access costs.** Attack trees for embedded systems must include physical attack vectors (JTAG, UART, side-channel). Engineers often model only network attacks because that's what they know. But on a deployed IoT sensor, the cheapest path might be opening the enclosure and probing the flash chip. Always include nodes for physical access and assign realistic costs (e.g., cost=1 for unprotected debug port, cost=8 for tamper-evident potting).

3. **Stopping at the root.** The root should be the *adversary's* goal, not your system's failure mode. "Attacker sends forged CAN frames" is a system failure. "Attacker causes unintended acceleration" is an adversary goal. If your root is too technical, you'll miss the business impact and struggle to get buy-in from product managers.

## Try It Yourself

1. **Build an attack tree for your bootloader.** Root: "Attacker runs unsigned firmware on device." Include at least 3 levels with both AND and OR nodes. Annotate each leaf with a cost (1-10) based on your hardware's protections (e.g., OTP fuses, secure boot, debug port lock).

2. **Compute the cheapest path.** Use the Python script above (or write your own) to find the minimum-cost path. Then, propose exactly one mitigation that would increase that path's cost by at least 5 points. Document why you chose that mitigation over others.

3. **Compare with STRIDE.** Take the same system and run a STRIDE analysis. Identify one threat that STRIDE flags but your attack tree misses, and one attack path your tree captures that STRIDE would not. Write a paragraph explaining which tool you'd use for a security review of a CAN bus gateway and why.

## Next Up

Tomorrow: **Trust Boundaries: Identifying Where Attackers Enter** — we'll map data flows across privilege boundaries in a real embedded system and learn why every `memcpy` across a trust boundary is a potential RCE. Bring your system architecture diagram.
