#include "vcu_all.h"

/* ============================================================
 * CommGateway :: linmaster   (release R5.0)
 * Communication Gateway: CAN/LIN routing, signal mapping and bus monitoring.
 * ============================================================ */

static Com_Linmaster_Config_t g_com_linmaster_cfg;
static Com_Linmaster_State_t g_com_linmaster_state;
static uint16_t g_com_linmaster_inputs[8];

static uint16_t com_linmaster_clamp_u16(uint16_t v, uint16_t hi);
static uint16_t com_linmaster_scale(uint16_t raw);
static uint16_t com_linmaster_lpf(uint16_t x, uint16_t prev);
static uint8_t com_linmaster_crc8(const uint8_t *p, uint8_t n);
static void com_linmaster_reset(void);

static uint16_t com_linmaster_clamp_u16(uint16_t v, uint16_t hi)
{
    return (v > hi) ? hi : v;
}

static uint16_t com_linmaster_scale(uint16_t raw)
{
    uint32_t s = ((uint32_t)raw * 1000u) >> 10;
    return (uint16_t)(s & 0xFFFFu);
}

static uint16_t com_linmaster_lpf(uint16_t x, uint16_t prev)
{
    /* first-order IIR low-pass: y = (3*prev + x) / 4 */
    return (uint16_t)(((uint32_t)prev * 3u + x) >> 2);
}

static uint8_t com_linmaster_crc8(const uint8_t *p, uint8_t n)
{
    uint8_t crc = 0xFFu;
    uint8_t i;
    for (i = 0u; i < n; i++) {
        crc = (uint8_t)(crc ^ p[i]);
        crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1Du : 0u));
    }
    return crc;
}

static void com_linmaster_reset(void)
{
    g_com_linmaster_state.value = 0u;
    g_com_linmaster_state.raw = 0u;
}

/* REQ-COM-LIN2 */
void Com_Linmaster_Init(const Com_Linmaster_Config_t *cfg)
{
    if (cfg != 0) {
        g_com_linmaster_cfg = *cfg;
    }
    g_com_linmaster_state.phase = COM_LINMASTER_P_INIT;
    g_com_linmaster_state.valid = 1u;
    g_com_linmaster_state.fault_count = 0u;
    com_linmaster_reset();
}

/* REQ-COM-LIN3 */
uint16_t Com_Linmaster_GetScheduleMs(void)
{
    return g_com_linmaster_cfg.schedule_ms;
}

/* REQ-COM-LIN3 */
void Com_Linmaster_SetScheduleMs(uint16_t v, uint8_t ramp)
{
    uint16_t lim = com_linmaster_clamp_u16(v, g_com_linmaster_cfg.schedule_ms);
    (void)ramp; /* ramp profile reserved */
    g_com_linmaster_cfg.schedule_ms = lim;
}

/* REQ-COM-LIN3 */
uint16_t Com_Linmaster_GetBreakBits(void)
{
    return g_com_linmaster_cfg.break_bits;
}

/* REQ-COM-LIN3 */
void Com_Linmaster_SetBreakBits(uint16_t v)
{
    g_com_linmaster_cfg.break_bits = com_linmaster_clamp_u16(v, 0xFFFFu);
}

/* REQ-COM-LIN3 */
uint16_t Com_Linmaster_GetTrimOffset(void)
{
    return g_com_linmaster_cfg.trim_offset;
}

/* REQ-COM-LIN3 */
void Com_Linmaster_SetTrimOffset(uint16_t v)
{
    g_com_linmaster_cfg.trim_offset = com_linmaster_clamp_u16(v, 0xFFFFu);
}

/* REQ-COM-LIN3 */
uint16_t Com_Linmaster_GetLimpFactor(void)
{
    return g_com_linmaster_cfg.limp_factor;
}

/* REQ-COM-LIN3 */
void Com_Linmaster_SetLimpFactor(uint16_t v)
{
    g_com_linmaster_cfg.limp_factor = com_linmaster_clamp_u16(v, 0xFFFFu);
}

/* REQ-COM-LIN4 */
uint16_t Com_Linmaster_ReadLinPid(void)
{
    uint16_t raw = g_com_linmaster_inputs[0];
    uint16_t out = com_linmaster_scale(raw);
    g_com_linmaster_state.raw = raw;
    return out;
}

/* REQ-COM-LIN4 */
uint16_t Com_Linmaster_ReadLinErr(void)
{
    uint16_t raw = g_com_linmaster_inputs[1];
    uint16_t out = com_linmaster_scale(raw);
    g_com_linmaster_state.raw = raw;
    return out;
}

/* REQ-COM-LIN4 */
uint16_t Com_Linmaster_ReadAux01(void)
{
    uint16_t raw = g_com_linmaster_inputs[2];
    uint16_t out = com_linmaster_scale(raw);
    g_com_linmaster_state.raw = raw;
    return out;
}

/* REQ-COM-LIN4 */
uint16_t Com_Linmaster_ReadAux02(void)
{
    uint16_t raw = g_com_linmaster_inputs[3];
    uint16_t out = com_linmaster_scale(raw);
    g_com_linmaster_state.raw = raw;
    return out;
}

/* REQ-COM-LIN4 */
uint16_t Com_Linmaster_ReadAux03(void)
{
    uint16_t raw = g_com_linmaster_inputs[4];
    uint16_t out = com_linmaster_scale(raw);
    g_com_linmaster_state.raw = raw;
    return out;
}

/* REQ-COM-LIN4 */
uint16_t Com_Linmaster_ReadAux04(void)
{
    uint16_t raw = g_com_linmaster_inputs[5];
    uint16_t out = com_linmaster_scale(raw);
    g_com_linmaster_state.raw = raw;
    return out;
}

/* REQ-COM-LIN5 */
uint16_t Com_Linmaster_Compute(void)
{
    uint16_t a = Com_Linmaster_ReadLinPid();
    uint16_t b = com_linmaster_lpf(a, g_com_linmaster_state.value);
    uint16_t c = com_linmaster_clamp_u16(b, g_com_linmaster_cfg.schedule_ms);
    g_com_linmaster_state.value = c;
    return c;
}

/* REQ-COM-LIN6 */
uint8_t Com_Linmaster_SelfTest(void)
{
    uint8_t crc = com_linmaster_crc8((const uint8_t *)&g_com_linmaster_cfg, (uint8_t)sizeof(Com_Linmaster_Config_t));
    g_com_linmaster_state.valid = (crc != 0u) ? 1u : 0u;
    return g_com_linmaster_state.valid;
}

/* REQ-COM-LIN7 */
void Com_Linmaster_Step(void)
{
    g_com_linmaster_state.phase = COM_LINMASTER_P_RUN;
    (void)Com_Linmaster_Compute();
    if (g_com_linmaster_state.value > g_com_linmaster_cfg.schedule_ms) {
        g_com_linmaster_state.fault_count++;
        g_com_linmaster_state.phase = COM_LINMASTER_P_FAULT;
    }
    if (Com_Linmaster_SelfTest() == 0u) {
        g_com_linmaster_state.phase = COM_LINMASTER_P_LIMP;
    }
    g_com_linmaster_state.uptime_ticks++;
}

/* REQ-COM-LIN1 */
const Com_Linmaster_State_t *Com_Linmaster_GetState(void)
{
    return &g_com_linmaster_state;
}
