---
title: "Day 06: Binding Documentation: Writing & Reading DT Bindings"
date: 2026-06-18
tags: ["til", "devicetree", "bindings", "documentation", "yaml"]
---

## What I Explored Today

Today I dove into the formal documentation system for Device Tree bindings — the YAML-based schema files that define what properties a node can have, what they mean, and how the kernel validates them. I’ve been writing `.dts` files for weeks, but I never truly understood the contract between the hardware description and the driver. That contract is the binding. I learned how to read existing bindings in `Documentation/devicetree/bindings/`, how to write a new one for a custom peripheral, and how to use `dt-validate` to check my work. This is the documentation layer that turns Device Tree from a wild west of random property names into a maintainable, verifiable system.

## The Core Concept

A Device Tree binding is a formal specification that says: *“If a node with compatible string `vendor,device` appears in the tree, these are the required and optional properties, their types, and their meanings.”* Without bindings, every driver author invents their own property names (`reg`, `interrupts`, `clocks` are standard, but what about `max-speed`, `gpio-line-names`, or `drive-strength`?). The binding document is the single source of truth.

Bindings serve three audiences:
1. **The kernel driver** — it knows exactly what properties to expect and how to parse them.
2. **The board designer** — they know what they must provide in the `.dts` file.
3. **The validation tools** — `dt-validate` can catch typos, missing properties, and type mismatches before the kernel boots.

The kernel community has standardized on **YAML** with a JSON Schema subset, stored in `Documentation/devicetree/bindings/`. Each binding file ends with `.yaml` and describes one or more compatible strings.

## Key Commands / Configuration / Code

### Reading an existing binding

Let’s look at a real binding for a GPIO controller. The file is `Documentation/devicetree/bindings/gpio/gpio-mockup.yaml` (simplified for clarity):

```yaml
# SPDX-License-Identifier: (GPL-2.0-only OR BSD-2-Clause)
%YAML 1.2
---
$id: http://devicetree.org/schemas/gpio/gpio-mockup.yaml#
$schema: http://devicetree.org/meta-schemas/core.yaml#

title: GPIO Mockup Device

maintainers:
  - Kamlakant Patel <kamlakant.patel@broadcom.com>

description: |
  This binding describes a virtual GPIO controller used for testing.
  It creates a set of GPIO lines that can be toggled from userspace.

properties:
  compatible:
    const: "gpio-mockup"

  gpio-controller: true

  "#gpio-cells":
    const: 2

  gpio-ranges:
    $ref: /schemas/types.yaml#/definitions/phandle-array
    description: |
      Specifies the GPIO line range. Format: <&gpio_controller base_pin count>

required:
  - compatible
  - gpio-controller
  - "#gpio-cells"

additionalProperties: false

examples:
  - |
    gpio_mockup: gpio-mockup {
        compatible = "gpio-mockup";
        gpio-controller;
        #gpio-cells = <2>;
        gpio-ranges = <&gpio_mockup 0 0 8>;
    };
```

Key takeaways:
- `properties` lists every allowed property. `const` means it must be exactly that string.
- `required` lists properties that must exist.
- `additionalProperties: false` means no unknown properties are allowed — strict validation.
- The `examples` block shows a valid node.

### Writing a new binding

Suppose I have a custom temperature sensor `mycorp,tmp100`. I create `Documentation/devicetree/bindings/iio/temperature/mycorp,tmp100.yaml`:

```yaml
# SPDX-License-Identifier: (GPL-2.0-only OR BSD-2-Clause)
%YAML 1.2
---
$id: http://devicetree.org/schemas/iio/temperature/mycorp,tmp100.yaml#
$schema: http://devicetree.org/meta-schemas/core.yaml#

title: MyCorp TMP100 Temperature Sensor

maintainers:
  - Your Name <you@example.com>

description: |
  The TMP100 is an I2C temperature sensor with ±0.5°C accuracy.
  Datasheet: https://example.com/tmp100.pdf

properties:
  compatible:
    const: "mycorp,tmp100"

  reg:
    maxItems: 1
    description: I2C slave address (0x48-0x4F)

  interrupts:
    maxItems: 1
    description: Optional alert interrupt

  vdd-supply:
    description: Regulator for the sensor power supply

  "#io-channel-cells":
    const: 1

required:
  - compatible
  - reg

additionalProperties: false

examples:
  - |
    i2c {
        #address-cells = <1>;
        #size-cells = <0>;

        temperature-sensor@48 {
            compatible = "mycorp,tmp100";
            reg = <0x48>;
            vdd-supply = <&vcc_3v3>;
            interrupt-parent = <&gpio1>;
            interrupts = <5 IRQ_TYPE_EDGE_FALLING>;
        };
    };
```

### Validating a DTS against bindings

```bash
# Install dt-schema tools (from devicetree-org/dt-schema)
pip install dtschema

# Validate a DTS file against all bindings
make dt_binding_check DT_SCHEMA_FILES=Documentation/devicetree/bindings/iio/temperature/mycorp,tmp100.yaml

# Validate a compiled DTB against bindings
make dtbs_check DT_SCHEMA_FILES=mycorp,tmp100.yaml
```

The `dt_binding_check` validates the YAML schema itself (syntax, references). The `dtbs_check` validates actual DTB files against the schema.

## Common Pitfalls & Gotchas

1. **Missing `additionalProperties: false`** — Without this, the validator will accept any random property you throw in. This defeats the purpose of a binding. Always set it unless you have a good reason (like a generic bus binding).

2. **Using `const` when you need `enum`** — If your device has multiple compatible strings (e.g., `"mycorp,tmp100"` and `"mycorp,tmp101"`), use `enum: ["mycorp,tmp100", "mycorp,tmp101"]` instead of `const`. `const` allows exactly one value.

3. **Forgetting to update the binding when adding a property** — The binding is a contract. If your driver starts reading a new `my-property` but the binding doesn’t list it, `dtbs_check` will fail for any DTS that uses it. Always update the binding in the same patch as the driver change.

4. **Incorrect `$ref` paths** — Many properties reuse common types (like `phandle-array`, `flag`, `uint32`). Use the correct `$ref` from `Documentation/devicetree/bindings/types.yaml`. A wrong path silently falls back to no type checking.

## Try It Yourself

1. **Read a real binding**: Open `Documentation/devicetree/bindings/i2c/i2c-gpio.yaml` in the Linux kernel source. Identify the required properties, the allowed optional properties, and the example. Write a minimal `.dts` fragment that would pass validation.

2. **Write a binding for a simple device**: Create a YAML binding for a hypothetical `mycorp,led` that has properties: `compatible` (const), `reg` (maxItems: 1), `label` (string), and `default-state` (enum: on, off, keep). Run `dt_binding_check` on it.

3. **Validate your own DTS**: Take a `.dts` file from a board you work on. Run `make dtbs_check DT_SCHEMA_FILES=all` and fix any warnings. You’ll likely find missing properties or typos.

## Next Up

Tomorrow we’ll cover **Common Bindings: GPIO, I2C, SPI, UART & Regulators** — the standard binding patterns you’ll use in almost every device tree. We’ll look at how `gpio-hog`, `reg`, `interrupts`, and `*-supply` are actually structured, and how to avoid the most common mistakes when wiring up peripherals.
