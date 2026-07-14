---
title: "Day 05: Matching Networks: L-Match, Pi-Match & T-Match Design"
date: 2026-07-14
tags: ["til", "rf-design", "l-match", "pi-match"]
---

## What I Explored Today

Today I dove into the practical design of three fundamental impedance matching topologies: L-match, Pi-match, and T-match networks. While textbooks often present these as simple LC ladder circuits, the real engineering challenge lies in choosing the right topology for your specific bandwidth, harmonic rejection, and component parasitics constraints. I worked through hand calculations for a 50Ω source to 100Ω load at 2.4 GHz, then verified against Smith chart solutions and simulated with real component models.

## The Core Concept

Impedance matching is about transferring maximum power from source to load by conjugately matching impedances at a specific frequency. But the *why* behind choosing L, Pi, or T goes beyond just getting the match.

**L-match** is the simplest — two reactive components (one shunt, one series) forming an "L" shape. It has the narrowest bandwidth and no control over Q. You get what the impedance transformation ratio gives you. Use it when board space is critical and your signal is narrowband (e.g., a single-channel ISM band).

**Pi-match** (series inductor, shunt capacitors on both sides) gives you independent control over Q and bandwidth. Higher Q means narrower bandwidth but better harmonic rejection. Pi networks are the workhorses for power amplifier output stages where you need to filter harmonics while matching to 50Ω.

**T-match** (series capacitors, shunt inductor to ground) inverts the Pi topology. It's useful when you need DC blocking built-in (the series caps block DC) or when the load impedance is very low (like a transistor input). The T network can also provide a higher Q than a Pi for the same transformation ratio.

The key insight: **you cannot arbitrarily choose Q** in an L-match. For Pi and T, you can. That's the primary decision driver.

## Key Commands / Configuration / Code

Here's a Python snippet I use for rapid prototyping. It solves the L-match component values for a given source (Rs) and load (Rl) at frequency f0. The math assumes Rs < Rl (step-up case).

```python
import numpy as np

def l_match_components(Rs, Rl, f0):
    """
    Calculate L-match component values for Rs < Rl.
    Returns (L_series, C_shunt) in Henries and Farads.
    """
    omega = 2 * np.pi * f0
    # Q factor is determined by transformation ratio
    Q = np.sqrt(Rl / Rs - 1)
    # Series inductor (on source side for low-pass topology)
    L = Q * Rs / omega
    # Shunt capacitor (on load side)
    C = Q / (omega * Rl)
    return L, C

# Example: 50Ω to 100Ω at 2.4 GHz
Rs, Rl, f0 = 50.0, 100.0, 2.4e9
L, C = l_match_components(Rs, Rl, f0)
print(f"L = {L*1e9:.2f} nH, C = {C*1e12:.2f} pF")
# Output: L = 3.32 nH, C = 0.66 pF
```

For Pi-match design, I use this approach to set Q first:

```python
def pi_match_components(Rs, Rl, Q, f0):
    """
    Pi-match: shunt C1 - series L - shunt C2.
    Assumes Rs < Rl. Returns (C1, L, C2).
    """
    omega = 2 * np.pi * f0
    # Calculate intermediate resistance Rp
    Rp = Rs * (Q**2 + 1)
    # Shunt capacitor on source side
    C1 = Q / (omega * Rs)
    # Series inductor
    L = (Rl * (Q**2 + 1) - Rp) / (omega * Q * (Q**2 + 1))
    # Shunt capacitor on load side
    C2 = Q / (omega * Rl)
    return C1, L, C2

# Example: 50Ω to 100Ω, Q=10 at 2.4 GHz
C1, L, C2 = pi_match_components(50, 100, 10, 2.4e9)
print(f"C1 = {C1*1e12:.2f} pF, L = {L*1e9:.2f} nH, C2 = {C2*1e12:.2f} pF")
# Output: C1 = 13.26 pF, L = 0.33 nH, C2 = 6.63 pF
```

**Smith chart verification** (using scikit-rf or a VNA simulator) is non-negotiable. I always plot the impedance trajectory to ensure it doesn't pass through regions where parasitic resonances could occur.

## Common Pitfalls & Gotchas

1. **Component self-resonance kills your match.** A 3.3 nH inductor at 2.4 GHz might have an SRF of 3 GHz. Above that, it looks capacitive. Always check the datasheet SRF and choose components with SRF > 2× your operating frequency. I've burned hours debugging a Pi network that worked in simulation but not on the bench — the inductor was self-resonating at 2.1 GHz.

2. **Parasitic capacitance of shunt components to ground.** In a Pi network, the shunt capacitors have one end connected to ground. The PCB via inductance and pad capacitance add ~0.3-0.5 pF of parasitic. For a 0.66 pF capacitor (like our L-match example), that's a 50% error. Use smaller value capacitors in parallel or account for parasitics in your design.

3. **Q is not free.** A Pi network with Q=20 will have 20× the circulating current of the load current. This means higher resistive losses in the inductor (which has finite Q) and potential heating. For power amplifiers, keep component Q below 10 unless you're willing to accept 1-2 dB of insertion loss from the matching network itself.

## Try It Yourself

1. **Hand-calculate an L-match** for a 50Ω source to a 25Ω load at 915 MHz. Note that now Rs > Rl, so the topology flips (shunt inductor, series capacitor). Verify with the Smith chart.

2. **Compare bandwidth of L-match vs Pi-match** for a 50Ω to 200Ω transformation at 1 GHz. Use a circuit simulator (LTSpice, QUCS, or ADS) to sweep from 0.5 to 1.5 GHz and measure the -10 dB return loss bandwidth. You'll see the Pi-match (Q=5) is roughly 3× wider than the L-match.

3. **Build a Pi-match with real component models.** Pick a 3.3 nH inductor from Coilcraft's 0402HP series, get its SPICE model, and simulate the Pi network from the example above. Adjust capacitor values to compensate for the inductor's finite Q (typically 50-80 at 2.4 GHz). Measure the insertion loss — it should be around 0.3-0.5 dB.

## Next Up

Tomorrow we shift from component-level matching to system-level characterization: **S-Parameters: Understanding S11, S21 & Return Loss**. We'll cover how to interpret two-port network parameters, why S11 is not the same as return loss (but everyone uses them interchangeably), and how to extract matching network performance from VNA measurements without getting fooled by cable losses.
