#include "vcu_all.h"

/* ============================================================
 * BatteryMgmt :: thermrunaway   (release R4.0)
 * Battery Management System: cell monitoring, state of charge, balancing and contactor control.
 * ============================================================ */

static Bms_Thermrunaway_Config_t g_bms_thermrunaway_cfg;
static Bms_Thermrunaway_State_t g_bms_thermrunaway_state;
static uint16_t g_bms_thermrunaway_inputs[8];

static uint16_t bms_thermrunaway_clamp_u16(uint16_t v, uint16_t hi);
static uint16_t bms_thermrunaway_scale(uint16_t raw);
static uint16_t bms_thermrunaway_lpf(uint16_t x, uint16_t prev);
static uint8_t bms_thermrunaway_crc8(const uint8_t *p, uint8_t n);
static void bms_thermrunaway_reset(void);

static uint16_t bms_thermrunaway_clamp_u16(uint16_t v, uint16_t hi)
{
    return (v > hi) ? hi : v;
}

static uint16_t bms_thermrunaway_scale(uint16_t raw)
{
    uint32_t s = ((uint32_t)raw * 1000u) >> 10;
    return (uint16_t)(s & 0xFFFFu);
}

static uint16_t bms_thermrunaway_lpf(uint16_t x, uint16_t prev)
{
    /* first-order IIR low-pass: y = (3*prev + x) / 4 */
    return (uint16_t)(((uint32_t)prev * 3u + x) >> 2);
}

static uint8_t bms_thermrunaway_crc8(const uint8_t *p, uint8_t n)
{
    uint8_t crc = 0xFFu;
    uint8_t i;
    for (i = 0u; i < n; i++) {
        crc = (uint8_t)(crc ^ p[i]);
        crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1Du : 0u));
    }
    return crc;
}

static void bms_thermrunaway_reset(void)
{
    g_bms_thermrunaway_state.value = 0u;
    g_bms_thermrunaway_state.raw = 0u;
}

/* REQ-BMS-THE2 */
void Bms_Thermrunaway_Init(const Bms_Thermrunaway_Config_t *cfg)
{
    if (cfg != 0) {
        g_bms_thermrunaway_cfg = *cfg;
    }
    g_bms_thermrunaway_state.phase = BMS_THERMRUNAWAY_P_INIT;
    g_bms_thermrunaway_state.valid = 1u;
    g_bms_thermrunaway_state.fault_count = 0u;
    bms_thermrunaway_reset();
}

/* REQ-BMS-THE3 */
uint16_t Bms_Thermrunaway_GetRunawayDtC(void)
{
    return g_bms_thermrunaway_cfg.runaway_dt_c;
}

/* REQ-BMS-THE3 */
void Bms_Thermrunaway_SetRunawayDtC(uint16_t v, uint8_t ramp)
{
    uint16_t lim = bms_thermrunaway_clamp_u16(v, g_bms_thermrunaway_cfg.runaway_dt_c);
    (void)ramp; /* ramp profile reserved */
    g_bms_thermrunaway_cfg.runaway_dt_c = lim;
}

/* REQ-BMS-THE3 */
uint16_t Bms_Thermrunaway_GetRunawayWindowMs(void)
{
    return g_bms_thermrunaway_cfg.runaway_window_ms;
}

/* REQ-BMS-THE3 */
void Bms_Thermrunaway_SetRunawayWindowMs(uint16_t v)
{
    g_bms_thermrunaway_cfg.runaway_window_ms = bms_thermrunaway_clamp_u16(v, 0xFFFFu);
}

/* REQ-BMS-THE3 */
uint16_t Bms_Thermrunaway_GetTrimOffset(void)
{
    return g_bms_thermrunaway_cfg.trim_offset;
}

/* REQ-BMS-THE3 */
void Bms_Thermrunaway_SetTrimOffset(uint16_t v)
{
    g_bms_thermrunaway_cfg.trim_offset = bms_thermrunaway_clamp_u16(v, 0xFFFFu);
}

/* REQ-BMS-THE4 */
uint16_t Bms_Thermrunaway_ReadDtDtC(void)
{
    uint16_t raw = g_bms_thermrunaway_inputs[0];
    uint16_t out = bms_thermrunaway_scale(raw);
    g_bms_thermrunaway_state.raw = raw;
    return out;
}

/* REQ-BMS-THE4 */
uint16_t Bms_Thermrunaway_ReadGasSensor(void)
{
    uint16_t raw = g_bms_thermrunaway_inputs[1];
    uint16_t out = bms_thermrunaway_scale(raw);
    g_bms_thermrunaway_state.raw = raw;
    return out;
}

/* REQ-BMS-THE4 */
uint16_t Bms_Thermrunaway_ReadAux01(void)
{
    uint16_t raw = g_bms_thermrunaway_inputs[2];
    uint16_t out = bms_thermrunaway_scale(raw);
    g_bms_thermrunaway_state.raw = raw;
    return out;
}

/* REQ-BMS-THE4 */
uint16_t Bms_Thermrunaway_ReadAux02(void)
{
    uint16_t raw = g_bms_thermrunaway_inputs[3];
    uint16_t out = bms_thermrunaway_scale(raw);
    g_bms_thermrunaway_state.raw = raw;
    return out;
}

/* REQ-BMS-THE4 */
uint16_t Bms_Thermrunaway_ReadAux03(void)
{
    uint16_t raw = g_bms_thermrunaway_inputs[4];
    uint16_t out = bms_thermrunaway_scale(raw);
    g_bms_thermrunaway_state.raw = raw;
    return out;
}

/* REQ-BMS-THE5 */
uint16_t Bms_Thermrunaway_Compute(void)
{
    uint16_t a = Bms_Thermrunaway_ReadDtDtC();
    uint16_t b = bms_thermrunaway_lpf(a, g_bms_thermrunaway_state.value);
    uint16_t c = bms_thermrunaway_clamp_u16(b, g_bms_thermrunaway_cfg.runaway_dt_c);
    g_bms_thermrunaway_state.value = c;
    return c;
}

/* REQ-BMS-THE6 */
uint8_t Bms_Thermrunaway_SelfTest(void)
{
    uint8_t crc = bms_thermrunaway_crc8((const uint8_t *)&g_bms_thermrunaway_cfg, (uint8_t)sizeof(Bms_Thermrunaway_Config_t));
    g_bms_thermrunaway_state.valid = (crc != 0u) ? 1u : 0u;
    return g_bms_thermrunaway_state.valid;
}

/* REQ-BMS-THE7 */
void Bms_Thermrunaway_Step(void)
{
    g_bms_thermrunaway_state.phase = BMS_THERMRUNAWAY_P_RUN;
    (void)Bms_Thermrunaway_Compute();
    if (g_bms_thermrunaway_state.value > g_bms_thermrunaway_cfg.runaway_dt_c) {
        g_bms_thermrunaway_state.fault_count++;
        g_bms_thermrunaway_state.phase = BMS_THERMRUNAWAY_P_FAULT;
    }
    if (Bms_Thermrunaway_SelfTest() == 0u) {
        g_bms_thermrunaway_state.phase = BMS_THERMRUNAWAY_P_LIMP;
    }
    g_bms_thermrunaway_state.uptime_ticks++;
}

/* REQ-BMS-THE1 */
const Bms_Thermrunaway_State_t *Bms_Thermrunaway_GetState(void)
{
    return &g_bms_thermrunaway_state;
}
