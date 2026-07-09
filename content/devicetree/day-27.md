---
title: "Day 27: Binding Documentation: Writing & Reading DT Bindings"
date: 2026-07-09
tags: ["til", "devicetree", "bindings", "documentation", "yaml"]
---

## What I Explored Today

Device Tree bindings are the contract between hardware description and driver code, but they're also the most neglected part of the DT ecosystem. Today I dove deep into how bindings are documented using the YAML schema format (DT-schema), how to read existing bindings to understand what a driver expects, and how to write a new binding from scratch. I discovered that the kernel's `dt-bindings` directory is essentially a machine-verifiable API specification, and learning to read it properly saves hours of driver debugging.

## The Core Concept

Bindings exist because a Device Tree `.dts` file is just data — it has no inherent meaning. A node with `compatible = "vendor,device"` tells the kernel *which* driver to load, but the binding tells both the developer and the kernel *what properties that node must and may contain*. Without bindings, you're guessing at property names, units, and required fields.

The modern binding format is YAML, validated by `dt-schema` tools. Why YAML? Because it's human-readable, machine-parseable, and allows formal constraints: "this property must be a 32-bit integer," "this property is required if the device is on an I2C bus," "these two properties are mutually exclusive." The old free-form text bindings (in `Documentation/devicetree/bindings/`) are being deprecated in favor of `.yaml` schemas that can be checked automatically by `dt_binding_check` and `dtbs_check`.

The real power: when you write a binding correctly, `make dtbs_check` will catch DTS errors before you ever flash the image. This is the difference between a 10-minute debug session and a 3-day hair-pulling exercise.

## Key Commands / Configuration / Code

### Reading an existing binding

```bash
# Find the binding for a specific compatible string
find Documentation/devicetree/bindings/ -name "*.yaml" | xargs grep -l "vendor,device"

# Example: GPIO controller binding
cat Documentation/devicetree/bindings/gpio/gpio-dwapb.yaml
```

### Anatomy of a YAML binding

```yaml
# SPDX-License-Identifier: (GPL-2.0-only OR BSD-2-Clause)
%YAML 1.2
---
$id: http://devicetree.org/schemas/example/my-device.yaml#
$schema: http://devicetree.org/meta-schemas/core.yaml#

title: My Custom Device Binding

maintainers:
  - Your Name <your.email@company.com>

description: |
  This binding describes a custom I2C temperature sensor with
  alarm output. The device supports both 12-bit and 14-bit
  conversion modes.

properties:
  compatible:
    const: vendor,my-device

  reg:
    maxItems: 1
    description: I2C slave address (0x48-0x4F)

  interrupts:
    maxItems: 1
    description: Active-low alarm interrupt

  vdd-supply:
    $ref: /schemas/types.yaml#/definitions/phandle
    description: Regulator supplying the VDD pin

  conversion-mode:
    $ref: /schemas/types.yaml#/definitions/uint32
    enum: [0, 1]           # 0=12-bit, 1=14-bit
    default: 0
    description: ADC resolution mode

required:
  - compatible
  - reg
  - vdd-supply

additionalProperties: false

examples:
  - |
    i2c {
        #address-cells = <1>;
        #size-cells = <0>;

        temp-sensor@48 {
            compatible = "vendor,my-device";
            reg = <0x48>;
            interrupts = <5 IRQ_TYPE_EDGE_FALLING>;
            vdd-supply = <&vcc_3v3>;
            conversion-mode = <1>;
        };
    };
```

### Validating your binding

```bash
# Check the YAML schema itself is valid
make dt_binding_check DT_SCHEMA_FILES=Documentation/devicetree/bindings/example/my-device.yaml

# Check a DTS against all bindings
make dtbs_check DT_SCHEMA_FILES=Documentation/devicetree/bindings/example/my-device.yaml

# Validate a single DTS file
dt-validate -s Documentation/devicetree/bindings/example/my-device.yaml arch/arm/boot/dts/my-board.dts
```

### Key schema constructs

```yaml
# Property types (from dt-schema)
properties:
  # Simple types
  my-uint32:
    $ref: /schemas/types.yaml#/definitions/uint32
    maximum: 0xFFFFFFFF

  my-string:
    $ref: /schemas/types.yaml#/definitions/string
    enum: ["option-a", "option-b"]

  my-phandle:
    $ref: /schemas/types.yaml#/definitions/phandle

  # Conditional requirements (if/then/else)
  my-gpios:
    description: GPIO specifier for reset pin
    maxItems: 1

if:
  properties:
    compatible:
      contains:
        const: vendor,rev-b
then:
  required:
    - my-gpios
```

## Common Pitfalls & Gotchas

1. **Missing `additionalProperties: false`** — This is the #1 mistake. Without it, the schema will accept any random property you throw in the DTS node. The kernel's `dtbs_check` will pass, but the driver will silently ignore the misspelled property. Always set `additionalProperties: false` unless you explicitly want to allow vendor-specific extensions.

2. **Using `const` when you need `enum`** — If your compatible string is `vendor,device-v1` and `vendor,device-v2`, don't use `const` for the compatible property. Use `enum: ["vendor,device-v1", "vendor,device-v2"]`. `const` means exactly one value, and the schema will reject any DTS using the other variant.

3. **Forgetting `#address-cells` and `#size-cells` in examples** — The example section is validated too. If your device is on a bus (I2C, SPI, etc.), you must include the parent bus node with proper `#address-cells` and `#size-cells`. The most common validation error is "example node has incorrect #address-cells" because people copy-paste without the parent context.

4. **Mixing up `maxItems` and `minItems`** — For a property that is a list (like `reg` or `interrupts`), `maxItems` sets the upper bound, `minItems` sets the lower bound. If you want exactly 2 entries, use `minItems: 2` and `maxItems: 2`. Omitting `minItems` means 0 entries are allowed, which is rarely what you want for required properties.

## Try It Yourself

1. **Read an existing binding**: Navigate to `Documentation/devicetree/bindings/i2c/` and pick any `.yaml` file. Identify the `required` properties and the `if/then/else` conditions. Then find a DTS file that uses that compatible string and verify it matches the schema.

2. **Write a binding for a fake device**: Create a YAML binding for an imaginary "vendor,my-led" device that has properties: `reg` (required, single cell), `led-gpios` (required, one GPIO), `brightness-max` (optional, uint32, default 255), and `color` (optional, string enum: "red", "green", "blue"). Validate it with `dt_binding_check`.

3. **Fix a broken binding**: Take the example binding from this post and remove `additionalProperties: false`. Add a misspelled property to the example (e.g., `vddd-supply`). Run `dtbs_check` on it and observe the warning. Then fix it by adding `additionalProperties: false` and re-validate.

## Next Up

Tomorrow we'll dive into **Common Bindings: GPIO, I2C, SPI, UART & Regulators** — the workhorse peripherals you'll encounter in every embedded Linux board. We'll cover the standard property patterns, how to read the pin controller bindings, and the subtle differences between legacy and new-style regulator bindings.
