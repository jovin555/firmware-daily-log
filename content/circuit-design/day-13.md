---
title: "Day 13: Digital Logic Design: Combinational vs Sequential Circuits"
date: 2026-07-22
tags: ["til", "circuit-design", "combinational", "sequential"]
---

## What I Explored Today

Today I dug into the fundamental taxonomy of digital logic: combinational versus sequential circuits. While both are built from the same primitive gates (AND, OR, NOT, NAND, NOR, XOR), they differ in one critical aspect—memory. Combinational circuits produce outputs that depend *only* on the current inputs; sequential circuits have outputs that depend on both current inputs *and* the circuit's past state. This distinction isn't academic—it determines whether your design can store data, sequence operations, or handle feedback. I spent the afternoon modeling both types in Verilog and testing them on a Spartan-7 FPGA to reinforce the practical boundary.

## The Core Concept

The why matters here: combinational logic is *stateless*. Think of an adder: given A=5 and B=3, it always outputs 8, regardless of what happened before. This makes combinational circuits predictable, glitch-prone (due to propagation delays), and easy to verify—just exhaust the truth table.

Sequential logic introduces *state* via feedback loops or clocked storage elements (flip-flops, latches). A counter, for example, increments on each clock edge; its output depends on the previous count. This statefulness enables finite state machines (FSMs), registers, and memory. The trade-off: sequential circuits require careful timing analysis (setup/hold times, clock skew) and are harder to debug because bugs can be state-dependent.

The key insight for engineers: **combinational logic defines the *next* state and outputs; sequential logic holds the *current* state.** In a synchronous system, combinational clouds compute the next value, and flip-flops update on the clock edge. This separation is the backbone of every CPU, GPU, and microcontroller.

## Key Commands / Configuration / Code

Below is a practical Verilog example contrasting a combinational 4-bit adder with a sequential 4-bit accumulator. I use this exact pattern in RTL design.

```verilog
// comb_adder.v — Pure combinational logic
module comb_adder (
    input  wire [3:0] a, b,
    output wire [3:0] sum,
    output wire       carry_out
);
    assign {carry_out, sum} = a + b;  // Continuous assignment, no clock
endmodule
```

```verilog
// seq_accumulator.v — Sequential logic with state
module seq_accumulator (
    input  wire       clk,
    input  wire       rst_n,          // active-low reset
    input  wire [3:0] data_in,
    output reg  [3:0] accum
);
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            accum <= 4'b0;            // reset state
        else
            accum <= accum + data_in; // state update on clock edge
    end
endmodule
```

**Simulation testbench snippet (Icarus Verilog):**
```bash
# Compile and run
iverilog -o tb.vvp comb_adder.v seq_accumulator.v testbench.v
vvp tb.vvp
gtkwave dump.vcd
```

In the testbench, apply `data_in = 4'd1` each cycle. The combinational adder outputs `sum = a+b` immediately; the accumulator increments by 1 each clock cycle, holding the running total.

## Common Pitfalls & Gotchas

1. **Latching inferred instead of flip-flop.**  
   In Verilog/VHDL, if you write `always @(*)` (combinational) but forget to assign a signal in every branch, the synthesizer infers a latch. This creates unintended sequential behavior. *Fix:* always assign default values at the top of the block, or use `always @(posedge clk)` for intended registers.

2. **Ignoring propagation delay in combinational chains.**  
   A deep chain of gates (e.g., 32-bit comparator) can exceed the clock period, causing setup violations. *Fix:* pipeline the logic (insert flip-flops between stages) or use faster logic families (e.g., LUT-based vs. ripple-carry).

3. **Clock domain crossing (CDC) without synchronization.**  
   Feeding a combinational output from one clock domain directly into a sequential circuit in another domain causes metastability. *Fix:* always use a two-flop synchronizer for single-bit signals, or an asynchronous FIFO for multi-bit buses.

## Try It Yourself

1. **Build a 4-bit ring counter.**  
   Implement a 4-bit shift register where the output of the last flip-flop feeds back to the input of the first. Initialize to `4'b0001` and observe the pattern on each clock edge. Use a D flip-flop array (not a behavioral shift operator) to understand the hardware structure.

2. **Design a combinational priority encoder (8-to-3).**  
   Write the truth table, then implement using `casez` or `assign` with ternary operators. Verify that when multiple inputs are high, only the highest-priority input appears on the output. Compare gate-level vs. behavioral simulation.

3. **Convert a Mealy FSM to Moore.**  
   Take a simple sequence detector (e.g., detect "101" on a serial line). Implement both Mealy (output depends on state + input) and Moore (output depends only on state). Note the difference in number of states and output timing.

## Next Up

Tomorrow, I’ll tackle **Clock Distribution & Crystal Oscillator Circuit Design**—how to generate a stable, low-jitter clock from a crystal, drive it into an FPGA or MCU, and avoid common PCB layout pitfalls that kill signal integrity. We’ll look at Pierce oscillator topology, load capacitance calculations, and clock buffer trees.
