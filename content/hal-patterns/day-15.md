---
title: "Day 15: Porting a HAL Across Vendors: STM32 HAL vs MCUXpresso vs nRFx"
date: 2026-07-15
tags: ["til", "hal-patterns", "multi-vendor", "porting"]
---

## What I Explored Today

I spent the day comparing three major vendor HALs—STM32 HAL (ST), MCUXpresso SDK (NXP), and nRFx SDK (Nordic)—to understand the real cost of porting a simple peripheral driver (UART TX) between them. The goal wasn't to pick a winner, but to catalog the mechanical differences in initialization, configuration structures, and error handling that make porting a non-trivial engineering task.

## The Core Concept

Every vendor HAL wraps the same hardware registers in a C API, but the *abstraction philosophy* diverges sharply. STM32 HAL uses a monolithic `HAL_UART_Init()` that takes a single handle and a massive config struct. MCUXpresso splits initialization into a clock config, a pin config, and a peripheral config—three separate structs and three init calls. nRFx is the leanest: you get a register-level struct (`NRF_UART_Type *`) and a minimal `nrf_uart_init()` that takes only a baud rate and a pin map.

The core challenge: **these HALs are not abstractions—they are thin, opinionated wrappers over vendor-specific register maps.** Porting isn't just changing function names; it’s restructuring how you think about initialization order, error propagation, and interrupt handling. A truly portable firmware layer must sit *above* these HALs, not replace them.

## Key Commands / Configuration / Code

Below is the same UART TX operation (8N1, 115200 baud, no flow control) implemented in each HAL. Notice the structural differences.

### STM32 HAL (STM32L4)

```c
// STM32 requires a handle, a config struct, and explicit GPIO init
UART_HandleTypeDef huart1;

void uart_init_stm32(void) {
    __HAL_RCC_USART1_CLK_ENABLE();
    __HAL_RCC_GPIOA_CLK_ENABLE();

    // GPIO pins must be configured separately
    GPIO_InitTypeDef gpio = {0};
    gpio.Pin = GPIO_PIN_9 | GPIO_PIN_10;  // TX=PA9, RX=PA10
    gpio.Mode = GPIO_MODE_AF_PP;
    gpio.Pull = GPIO_NOPULL;
    gpio.Speed = GPIO_SPEED_FREQ_VERY_HIGH;
    gpio.Alternate = GPIO_AF7_USART1;
    HAL_GPIO_Init(GPIOA, &gpio);

    // UART config is one monolithic struct
    huart1.Instance = USART1;
    huart1.Init.BaudRate = 115200;
    huart1.Init.WordLength = UART_WORDLENGTH_8B;
    huart1.Init.StopBits = UART_STOPBITS_1;
    huart1.Init.Parity = UART_PARITY_NONE;
    huart1.Init.Mode = UART_MODE_TX_RX;
    huart1.Init.HwFlowCtl = UART_HWCONTROL_NONE;
    HAL_UART_Init(&huart1);
}

void uart_send_stm32(uint8_t *data, uint16_t len) {
    // HAL_UART_Transmit returns HAL_StatusTypeDef (HAL_OK, HAL_ERROR, HAL_BUSY, HAL_TIMEOUT)
    HAL_UART_Transmit(&huart1, data, len, 1000);  // timeout in ms
}
```

### MCUXpresso SDK (LPC55S69)

```c
// MCUXpresso uses three separate config structs: clock, pin, and peripheral
uart_config_t uart_config;
clock_name_t uart_clock = kCLOCK_Flexcomm0;

void uart_init_mcux(void) {
    // Step 1: Enable clock to the Flexcomm peripheral
    CLOCK_AttachClk(kFRO12M_to_FLEXCOMM0);

    // Step 2: Configure pins via IOMUXC (pinmux driver)
    IOMUXC_SetPinMux(IOMUXC_PIO0_29_FLEXCOMM0_TXD, 0U);
    IOMUXC_SetPinMux(IOMUXC_PIO0_30_FLEXCOMM0_RXD, 0U);
    IOMUXC_SetPinConfig(IOMUXC_PIO0_29_FLEXCOMM0_TXD, 0x10B0U);  // pull-up, fast slew
    IOMUXC_SetPinConfig(IOMUXC_PIO0_30_FLEXCOMM0_RXD, 0x10B0U);

    // Step 3: Initialize UART with a separate config struct
    UART_GetDefaultConfig(&uart_config);
    uart_config.baudRate_Bps = 115200;
    uart_config.enableTx = true;
    uart_config.enableRx = true;
    UART_Init(USART0, &uart_config, CLOCK_GetFlexCommClkFreq(0));
}

void uart_send_mcux(uint8_t *data, uint32_t len) {
    // Returns status_t (kStatus_Success, kStatus_Fail, etc.)
    UART_WriteBlocking(USART0, data, len);
}
```

### nRFx SDK (nRF52840)

```c
// nRFx is minimal: no handle, no config struct—just a register pointer and a struct of pins
void uart_init_nrfx(void) {
    // nRF UART uses a "pins" struct with physical pin numbers
    nrf_uart_pins_t pins = {
        .txd = NRF_GPIO_PIN_MAP(0, 6),   // P0.06
        .rxd = NRF_GPIO_PIN_MAP(0, 8),   // P0.08
        .cts = NRF_UART_PSEL_DISCONNECTED,
        .rts = NRF_UART_PSEL_DISCONNECTED,
    };

    // nrf_uart_init takes baud rate, pins, interrupt priority, and a flag for blocking vs non-blocking
    ret_code_t err = nrf_uart_init(NRF_UART0, &pins, NRF_UART_BAUDRATE_115200,
                                   APP_IRQ_PRIORITY_LOW, false);  // false = no interrupt
    APP_ERROR_CHECK(err);  // macro that halts on error
}

void uart_send_nrfx(uint8_t *data, size_t len) {
    // nrf_uart_tx_blocking returns ret_code_t (NRF_SUCCESS or NRF_ERROR_*)
    ret_code_t err = nrf_uart_tx_blocking(NRF_UART0, data, len);
    APP_ERROR_CHECK(err);
}
```

## Common Pitfalls & Gotchas

1. **Error type mismatch** — STM32 returns `HAL_StatusTypeDef` (enum), MCUXpresso returns `status_t` (enum with different values), nRFx returns `ret_code_t` (uint32_t). You cannot write a generic error handler without a translation layer. A common mistake is to compare `HAL_OK` against `kStatus_Success` in a porting attempt—they are different values.

2. **Clock tree assumptions** — STM32 HAL often enables clocks implicitly inside `HAL_UART_Init()`, but MCUXpresso requires explicit `CLOCK_AttachClk()` calls *before* `UART_Init()`. If you port by copying the STM32 init order, the MCUXpresso UART will hang because the peripheral clock is gated.

3. **Pin mux granularity** — nRFx requires you to pass pin numbers *into* the init function. STM32 and MCUXpresso require separate GPIO/pinmux configuration *before* the UART init. If you forget to configure pins in STM32, the UART init may succeed but TX will be silent. In nRFx, the init itself will fail if the pin is invalid.

## Try It Yourself

1. **Port a UART echo** — Take a working UART echo loop from STM32 HAL and rewrite it for MCUXpresso. Pay attention to the clock and pin setup order. Run it on an LPC55S69-EVK or similar board.

2. **Build a HAL abstraction layer** — Write a `hal_uart_tx(uint8_t *data, uint32_t len)` function that compiles for all three platforms using `#ifdef` guards. Use a common error code enum (e.g., `HAL_UART_OK = 0, HAL_UART_TIMEOUT = 1`). This is the first step toward a portable driver.

3. **Compare interrupt-driven TX** — Implement a non-blocking UART TX with a TX complete callback in each HAL. STM32 uses `HAL_UART_Transmit_IT()`, MCUXpresso uses `UART_TransferSendNonBlocking()`, nRFx uses `nrf_uart_tx()` with interrupts enabled. Note how each HAL handles the callback registration.

## Next Up

Tomorrow: **Zephyr Device Driver Model: device_api & DEVICE_DT_DEFINE** — we’ll see how Zephyr’s devicetree-based driver model solves the portability problem by decoupling driver logic from vendor HALs entirely.
