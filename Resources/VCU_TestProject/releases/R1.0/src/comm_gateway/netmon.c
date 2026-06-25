#include "vcu_all.h"

/* ============================================================
 * CommGateway :: netmon   (release R1.0)
 * Communication Gateway: CAN/LIN routing, signal mapping and bus monitoring.
 * ============================================================ */

static Com_Netmon_Config_t g_com_netmon_cfg;
static Com_Netmon_State_t g_com_netmon_state;
static uint16_t g_com_netmon_inputs[8];

static uint16_t com_netmon_clamp_u16(uint16_t v, uint16_t hi);
static uint16_t com_netmon_scale(uint16_t raw);
static uint16_t com_netmon_lpf(uint16_t x, uint16_t prev);
static uint8_t com_netmon_crc8(const uint8_t *p, uint8_t n);
static void com_netmon_reset(void);

static uint16_t com_netmon_clamp_u16(uint16_t v, uint16_t hi)
{
    return (v > hi) ? hi : v;
}

static uint16_t com_netmon_scale(uint16_t raw)
{
    uint32_t s = ((uint32_t)raw * 1000u) >> 10;
    return (uint16_t)(s & 0xFFFFu);
}

static uint16_t com_netmon_lpf(uint16_t x, uint16_t prev)
{
    /* first-order IIR low-pass: y = (3*prev + x) / 4 */
    return (uint16_t)(((uint32_t)prev * 3u + x) >> 2);
}

static uint8_t com_netmon_crc8(const uint8_t *p, uint8_t n)
{
    uint8_t crc = 0xFFu;
    uint8_t i;
    for (i = 0u; i < n; i++) {
        crc = (uint8_t)(crc ^ p[i]);
        crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1Du : 0u));
    }
    return crc;
}

static void com_netmon_reset(void)
{
    g_com_netmon_state.value = 0u;
    g_com_netmon_state.raw = 0u;
}

/* REQ-COM-NET2 */
void Com_Netmon_Init(const Com_Netmon_Config_t *cfg)
{
    if (cfg != 0) {
        g_com_netmon_cfg = *cfg;
    }
    g_com_netmon_state.phase = COM_NETMON_P_INIT;
    g_com_netmon_state.valid = 1u;
    /* no fault counter pre-R2.0 */
    com_netmon_reset();
}

/* REQ-COM-NET3 */
uint16_t Com_Netmon_GetWakeTimeoutMs(void)
{
    return g_com_netmon_cfg.wake_timeout_ms;
}

/* REQ-COM-NET3 */
void Com_Netmon_SetWakeTimeoutMs(uint16_t v)
{
    g_com_netmon_cfg.wake_timeout_ms = com_netmon_clamp_u16(v, 0xFFFFu);
}

/* REQ-COM-NET3 */
uint16_t Com_Netmon_GetSleepDelayMs(void)
{
    return g_com_netmon_cfg.sleep_delay_ms;
}

/* REQ-COM-NET3 */
void Com_Netmon_SetSleepDelayMs(uint16_t v)
{
    g_com_netmon_cfg.sleep_delay_ms = com_netmon_clamp_u16(v, 0xFFFFu);
}

/* REQ-COM-NET4 */
uint16_t Com_Netmon_ReadBusActivity(void)
{
    uint16_t raw = g_com_netmon_inputs[0];
    uint16_t out = com_netmon_scale(raw);
    g_com_netmon_state.raw = raw;
    return out;
}

/* REQ-COM-NET4 */
uint16_t Com_Netmon_ReadWakeLine(void)
{
    uint16_t raw = g_com_netmon_inputs[1];
    uint16_t out = com_netmon_scale(raw);
    g_com_netmon_state.raw = raw;
    return out;
}

/* REQ-COM-NET5 */
uint16_t Com_Netmon_Compute(void)
{
    uint16_t a = Com_Netmon_ReadBusActivity();
    uint16_t b = com_netmon_lpf(a, g_com_netmon_state.value);
    uint16_t c = com_netmon_clamp_u16(b, g_com_netmon_cfg.wake_timeout_ms);
    g_com_netmon_state.value = c;
    return c;
}

/* REQ-COM-NET9 */
void Com_Netmon_LegacyReset(void)
{
    /* REQ-COM-NET9: deprecated legacy reset, removed in R2.0. */
    g_com_netmon_state.phase = COM_NETMON_P_OFF;
}

/* REQ-COM-NET7 */
void Com_Netmon_Step(void)
{
    g_com_netmon_state.phase = COM_NETMON_P_RUN;
    (void)Com_Netmon_Compute();
}

/* REQ-COM-NET1 */
const Com_Netmon_State_t *Com_Netmon_GetState(void)
{
    return &g_com_netmon_state;
}
