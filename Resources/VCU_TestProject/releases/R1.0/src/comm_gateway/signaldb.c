#include "vcu_all.h"

/* ============================================================
 * CommGateway :: signaldb   (release R1.0)
 * Communication Gateway: CAN/LIN routing, signal mapping and bus monitoring.
 * ============================================================ */

static Com_Signaldb_Config_t g_com_signaldb_cfg;
static Com_Signaldb_State_t g_com_signaldb_state;
static uint16_t g_com_signaldb_inputs[8];

static uint16_t com_signaldb_clamp_u16(uint16_t v, uint16_t hi);
static uint16_t com_signaldb_scale(uint16_t raw);
static uint16_t com_signaldb_lpf(uint16_t x, uint16_t prev);
static uint8_t com_signaldb_crc8(const uint8_t *p, uint8_t n);
static void com_signaldb_reset(void);

static uint16_t com_signaldb_clamp_u16(uint16_t v, uint16_t hi)
{
    return (v > hi) ? hi : v;
}

static uint16_t com_signaldb_scale(uint16_t raw)
{
    uint32_t s = ((uint32_t)raw * 1000u) >> 10;
    return (uint16_t)(s & 0xFFFFu);
}

static uint16_t com_signaldb_lpf(uint16_t x, uint16_t prev)
{
    /* first-order IIR low-pass: y = (3*prev + x) / 4 */
    return (uint16_t)(((uint32_t)prev * 3u + x) >> 2);
}

static uint8_t com_signaldb_crc8(const uint8_t *p, uint8_t n)
{
    uint8_t crc = 0xFFu;
    uint8_t i;
    for (i = 0u; i < n; i++) {
        crc = (uint8_t)(crc ^ p[i]);
        crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1Du : 0u));
    }
    return crc;
}

static void com_signaldb_reset(void)
{
    g_com_signaldb_state.value = 0u;
    g_com_signaldb_state.raw = 0u;
}

/* REQ-COM-SIG2 */
void Com_Signaldb_Init(const Com_Signaldb_Config_t *cfg)
{
    if (cfg != 0) {
        g_com_signaldb_cfg = *cfg;
    }
    g_com_signaldb_state.phase = COM_SIGNALDB_P_INIT;
    g_com_signaldb_state.valid = 1u;
    /* no fault counter pre-R2.0 */
    com_signaldb_reset();
}

/* REQ-COM-SIG3 */
uint16_t Com_Signaldb_GetTimeoutMs(void)
{
    return g_com_signaldb_cfg.timeout_ms;
}

/* REQ-COM-SIG3 */
void Com_Signaldb_SetTimeoutMs(uint16_t v)
{
    g_com_signaldb_cfg.timeout_ms = com_signaldb_clamp_u16(v, 0xFFFFu);
}

/* REQ-COM-SIG3 */
uint16_t Com_Signaldb_GetDefaultValue(void)
{
    return g_com_signaldb_cfg.default_value;
}

/* REQ-COM-SIG3 */
void Com_Signaldb_SetDefaultValue(uint16_t v)
{
    g_com_signaldb_cfg.default_value = com_signaldb_clamp_u16(v, 0xFFFFu);
}

/* REQ-COM-SIG4 */
uint16_t Com_Signaldb_ReadRawA(void)
{
    uint16_t raw = g_com_signaldb_inputs[0];
    uint16_t out = com_signaldb_scale(raw);
    g_com_signaldb_state.raw = raw;
    return out;
}

/* REQ-COM-SIG4 */
uint16_t Com_Signaldb_ReadRawB(void)
{
    uint16_t raw = g_com_signaldb_inputs[1];
    uint16_t out = com_signaldb_scale(raw);
    g_com_signaldb_state.raw = raw;
    return out;
}

/* REQ-COM-SIG4 */
uint16_t Com_Signaldb_ReadRawC(void)
{
    uint16_t raw = g_com_signaldb_inputs[2];
    uint16_t out = com_signaldb_scale(raw);
    g_com_signaldb_state.raw = raw;
    return out;
}

/* REQ-COM-SIG5 */
uint16_t Com_Signaldb_Compute(void)
{
    uint16_t a = Com_Signaldb_ReadRawA();
    uint16_t b = com_signaldb_lpf(a, g_com_signaldb_state.value);
    uint16_t c = com_signaldb_clamp_u16(b, g_com_signaldb_cfg.timeout_ms);
    g_com_signaldb_state.value = c;
    return c;
}

/* REQ-COM-SIG9 */
void Com_Signaldb_LegacyReset(void)
{
    /* REQ-COM-SIG9: deprecated legacy reset, removed in R2.0. */
    g_com_signaldb_state.phase = COM_SIGNALDB_P_OFF;
}

/* REQ-COM-SIG7 */
void Com_Signaldb_Step(void)
{
    g_com_signaldb_state.phase = COM_SIGNALDB_P_RUN;
    (void)Com_Signaldb_Compute();
}

/* REQ-COM-SIG1 */
const Com_Signaldb_State_t *Com_Signaldb_GetState(void)
{
    return &g_com_signaldb_state;
}
