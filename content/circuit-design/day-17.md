---
title: "Day 17: Motor Driver Circuits: H-Bridges & Gate Drivers"
date: 2026-07-28
tags: ["til", "circuit-design", "h-bridge", "gate-driver"]
---

## What I Explored Today

Today I dug into the practical realities of driving DC motors with H-bridge circuits and the gate driver ICs that make them work reliably. After spending yesterday modeling motor back-EMF and stall currents, I needed to actually switch the damn things without letting the magic smoke out. I prototyped two configurations: a discrete N-channel/P-channel H-bridge for a 12V, 2A brushed DC motor, and a dedicated gate-driver IC (the TI DRV8871) for comparison. The difference in switching behavior, dead-time management, and shoot-through prevention was stark.

## The Core Concept

An H-bridge is conceptually simple—four switches arranged in an "H" shape to let current flow through a motor in either direction. But the *why* of proper gate driving is where most engineers get burned.

The fundamental problem: MOSFET gates are capacitors. A typical power MOSFET has 1-10 nF of input capacitance. To switch it on fast enough to avoid linear-region operation (where it dissipates massive heat), you need a gate driver that can source and sink several amps momentarily. Your microcontroller's GPIO pin, rated for 4-8 mA, will take microseconds to charge that gate—time during which the MOSFET sits in its ohmic-to-saturation transition, dissipating I²R losses that can exceed 50W for a brief but destructive instant.

The second critical issue is shoot-through. When you turn off the high-side MOSFET and turn on the low-side, there's a moment where both could be partially conducting. This creates a dead short across your power supply. The solution is *dead time*—a deliberate delay between switching one FET off and the other on. Integrated gate drivers handle this with precision; discrete designs require careful RC timing or software delays.

Finally, bootstrap capacitors for high-side N-channel MOSFETs. You can't drive an N-channel gate above the source voltage without a charge pump or bootstrap circuit. The bootstrap cap charges through a diode when the low-side FET is on, then floats up to provide gate drive when the high-side needs to conduct. If your PWM duty cycle is too high or too low, the bootstrap cap doesn't get enough refresh time, and your high-side FET drops out.

## Key Commands / Configuration / Code

Here's a practical discrete H-bridge gate drive using the IR2104 half-bridge driver, which handles dead-time and bootstrap automatically:

```c
// IR2104 Half-Bridge Driver Configuration for 12V DC Motor
// Pin connections:
//   IR2104 IN  -> MCU GPIO (PWM signal)
//   IR2104 SD  -> MCU GPIO (shutdown, active low)
//   IR2104 VB  -> Bootstrap capacitor (10uF + 100nF) to VS
//   IR2104 VS  -> High-side source / motor terminal
//   IR2104 HO  -> High-side gate (IRFZ44N N-channel)
//   IR2104 LO  -> Low-side gate (IRFZ44N N-channel)
//   IR2104 VCC -> 12V supply (via 100nF decoupling cap to COM)

// GPIO initialization
#define PWM_PIN     PB1  // Timer1 OC1A output
#define SD_PIN      PD2  // Shutdown control

void motor_init(void) {
    // Set shutdown pin high to enable driver
    DDRD |= (1 << SD_PIN);
    PORTD |= (1 << SD_PIN);
    
    // Configure Timer1 for 20kHz PWM on PB1
    TCCR1A = (1 << WGM11) | (1 << COM1A1);  // Fast PWM, top=ICR1
    TCCR1B = (1 << WGM13) | (1 << WGM12) | (1 << CS11);  // Prescaler=8
    ICR1 = 100;  // 20kHz: 16MHz / (8 * 100) = 20,000 Hz
    OCR1A = 0;   // Start with 0% duty cycle
}

void motor_set_speed(int16_t speed) {
    // speed: -1000 to +1000 (negative = reverse direction)
    // For simplicity, we use two H-bridges: one for forward, one for reverse
    // In practice, use a single H-bridge with direction pin
    
    if (speed > 0) {
        // Forward: PWM on high-side, low-side on
        OCR1A = (speed * 100) / 1000;  // Scale to 0-100
        // Direction control via second IR2104 or relay
    } else if (speed < 0) {
        // Reverse: PWM on opposite half-bridge
        OCR1A = (-speed * 100) / 1000;
    } else {
        // Brake: short motor terminals via both low-side FETs
        OCR1A = 0;
        // Set both low-side gates high (coast vs brake)
    }
}

// Critical: Ensure dead-time is respected
// IR2104 has ~520ns built-in dead time - adequate for 20kHz
// For custom discrete drivers, add this in software:
void safe_pwm_update(uint8_t new_duty) {
    static uint8_t last_duty = 0;
    if (new_duty == 0 && last_duty > 0) {
        // Force low-side on for 1us before allowing high-side again
        _delay_us(1);
    }
    last_duty = new_duty;
    OCR1A = new_duty;
}
```

For a fully integrated solution, the DRV8871 simplifies everything:

```c
// DRV8871 Configuration - No external FETs needed
// Pin connections:
//   DRV8871 IN1 -> MCU GPIO (PWM/direction)
//   DRV8871 IN2 -> MCU GPIO (PWM/direction)
//   DRV8871 nSLEEP -> MCU GPIO (high to enable)
//   DRV8871 VREF -> Analog voltage or PWM for current limit
//   DRV8871 IPROPI -> ADC pin (current sense output)

void drv8871_init(void) {
    // Enable device
    DDRD |= (1 << PD3);  // nSLEEP
    PORTD |= (1 << PD3); // Wake up
    
    // Set current limit via VREF (3.3V = 3.65A limit)
    // VREF = I_LIMIT * 10k / 11000  (from datasheet)
    // For 2A limit: VREF = 2 * 11000 / 10000 = 2.2V
    // Use DAC or PWM-filter to set this
}

void drv8871_set_speed(int16_t speed) {
    // speed: -255 to +255
    if (speed > 0) {
        // Forward: IN1=PWM, IN2=LOW
        OCR0A = speed;  // Timer0 PWM on IN1
        PORTD &= ~(1 << PD4); // IN2 low
    } else if (speed < 0) {
        // Reverse: IN1=LOW, IN2=PWM
        OCR0A = -speed;
        PORTD |= (1 << PD4); // IN2 high for reverse PWM
    } else {
        // Brake (both inputs high) or Coast (both low)
        PORTD &= ~(1 << PD4);
        OCR0A = 0;
    }
}
```

## Common Pitfalls & Gotchas

**1. Bootstrap starvation at extreme duty cycles.** If your PWM goes above 95% duty, the low-side FET doesn't stay on long enough to recharge the bootstrap capacitor. The high-side gate voltage droops, the FET enters linear mode, and it overheats in seconds. Solution: limit PWM to 90-95% max, or use a charge pump that doesn't depend on switching.

**2. Gate ringing from parasitic inductance.** Long traces between the gate driver output and the MOSFET gate form an LC tank with the gate capacitance. I've seen 5V of gate overvoltage on a 12V gate drive—enough to blow the gate oxide on logic-level FETs. Always place a 10-22 ohm series gate resistor physically close to the MOSFET gate to dampen ringing.

**3. Shoot-through from insufficient dead time.** The IR2104's 520ns dead time works for most low-frequency designs, but at >50kHz PWM, that's a significant portion of the switching period. If you're using discrete components or a microcontroller to generate dead time, remember that GPIO rise/fall times and comparator propagation delays eat into your margin. Measure the actual cross-conduction current with a current probe—if you see spikes at every switching edge, increase dead time.

## Try It Yourself

1. **Measure bootstrap voltage decay.** Build the IR2104 circuit above, run at 95% duty cycle, and probe the VB-VS voltage with an oscilloscope (differential probe or math channel). Watch it droop below 10V and observe the motor current ripple increase.

2. **Characterize dead time with a logic analyzer.** On a discrete H-bridge built from two half-bridge drivers, measure the time between the falling edge of one gate signal and the rising edge of the complementary gate. Adjust your software delay until you see exactly 500ns of gap—then check for shoot-through current.

3. **Compare integrated vs. discrete efficiency.** Drive the same motor at 50% PWM, 1A load, using the DRV8871 and your discrete IR2104 design. Measure the junction temperature of the FETs (or IC) with a thermal camera after 5 minutes. Calculate the power dissipation difference and identify where the losses occur.

## Next Up

Tomorrow I'm tackling **MOSFET Selection & Switching Circuit Design**—the practical process of choosing the right FET for your load, calculating gate charge requirements, designing snubbers for ringing, and laying out a PCB that doesn't oscillate at 100MHz. We'll compare logic-level vs. standard gate thresholds and work through a real 24V, 5A motor driver design from datasheet to prototype.
