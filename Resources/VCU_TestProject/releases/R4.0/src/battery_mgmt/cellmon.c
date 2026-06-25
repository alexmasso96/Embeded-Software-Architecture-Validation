#include "vcu_all.h"

/* ============================================================
 * BatteryMgmt :: cellmon   (release R4.0)
 * Battery Management System: cell monitoring, state of charge, balancing and contactor control.
 * ============================================================ */

static Bms_Cellmon_Config_t g_bms_cellmon_cfg;
static Bms_Cellmon_State_t g_bms_cellmon_state;
static uint16_t g_bms_cellmon_inputs[8];

static uint16_t bms_cellmon_clamp_u16(uint16_t v, uint16_t hi);
static uint16_t bms_cellmon_scale(uint16_t raw);
static uint16_t bms_cellmon_lpf(uint16_t x, uint16_t prev);
static uint8_t bms_cellmon_crc8(const uint8_t *p, uint8_t n);
static void bms_cellmon_reset(void);

static uint16_t bms_cellmon_clamp_u16(uint16_t v, uint16_t hi)
{
    return (v > hi) ? hi : v;
}

static uint16_t bms_cellmon_scale(uint16_t raw)
{
    uint32_t s = ((uint32_t)raw * 1000u) >> 10;
    return (uint16_t)(s & 0xFFFFu);
}

static uint16_t bms_cellmon_lpf(uint16_t x, uint16_t prev)
{
    /* first-order IIR low-pass: y = (3*prev + x) / 4 */
    return (uint16_t)(((uint32_t)prev * 3u + x) >> 2);
}

static uint8_t bms_cellmon_crc8(const uint8_t *p, uint8_t n)
{
    uint8_t crc = 0xFFu;
    uint8_t i;
    for (i = 0u; i < n; i++) {
        crc = (uint8_t)(crc ^ p[i]);
        crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1Du : 0u));
    }
    return crc;
}

static void bms_cellmon_reset(void)
{
    g_bms_cellmon_state.value = 0u;
    g_bms_cellmon_state.raw = 0u;
}

/* REQ-BMS-CEL2 */
void Bms_Cellmon_Init(const Bms_Cellmon_Config_t *cfg)
{
    if (cfg != 0) {
        g_bms_cellmon_cfg = *cfg;
    }
    g_bms_cellmon_state.phase = BMS_CELLMON_P_INIT;
    g_bms_cellmon_state.valid = 1u;
    g_bms_cellmon_state.fault_count = 0u;
    bms_cellmon_reset();
}

/* REQ-BMS-CEL3 */
uint16_t Bms_Cellmon_GetOverVoltMv(void)
{
    return g_bms_cellmon_cfg.over_volt_mv;
}

/* REQ-BMS-CEL3 */
void Bms_Cellmon_SetOverVoltMv(uint16_t v, uint8_t ramp)
{
    uint16_t lim = bms_cellmon_clamp_u16(v, g_bms_cellmon_cfg.over_volt_mv);
    (void)ramp; /* ramp profile reserved */
    g_bms_cellmon_cfg.over_volt_mv = lim;
}

/* REQ-BMS-CEL3 */
uint16_t Bms_Cellmon_GetUnderVoltMv(void)
{
    return g_bms_cellmon_cfg.under_volt_mv;
}

/* REQ-BMS-CEL3 */
void Bms_Cellmon_SetUnderVoltMv(uint16_t v)
{
    g_bms_cellmon_cfg.under_volt_mv = bms_cellmon_clamp_u16(v, 0xFFFFu);
}

/* REQ-BMS-CEL3 */
uint16_t Bms_Cellmon_GetSampleMs(void)
{
    return g_bms_cellmon_cfg.sample_ms;
}

/* REQ-BMS-CEL3 */
void Bms_Cellmon_SetSampleMs(uint16_t v)
{
    g_bms_cellmon_cfg.sample_ms = bms_cellmon_clamp_u16(v, 0xFFFFu);
}

/* REQ-BMS-CEL3 */
uint16_t Bms_Cellmon_GetTrimOffset(void)
{
    return g_bms_cellmon_cfg.trim_offset;
}

/* REQ-BMS-CEL3 */
void Bms_Cellmon_SetTrimOffset(uint16_t v)
{
    g_bms_cellmon_cfg.trim_offset = bms_cellmon_clamp_u16(v, 0xFFFFu);
}

/* REQ-BMS-CEL4 */
uint16_t Bms_Cellmon_ReadCellMv(void)
{
    uint16_t raw = g_bms_cellmon_inputs[0];
    uint16_t out = bms_cellmon_scale(raw);
    g_bms_cellmon_state.raw = raw;
    return out;
}

/* REQ-BMS-CEL4 */
uint16_t Bms_Cellmon_ReadPackCurrent(void)
{
    uint16_t raw = g_bms_cellmon_inputs[1];
    uint16_t out = bms_cellmon_scale(raw);
    g_bms_cellmon_state.raw = raw;
    return out;
}

/* REQ-BMS-CEL4 */
uint16_t Bms_Cellmon_ReadCellTemp(void)
{
    uint16_t raw = g_bms_cellmon_inputs[2];
    uint16_t out = bms_cellmon_scale(raw);
    g_bms_cellmon_state.raw = raw;
    return out;
}

/* REQ-BMS-CEL4 */
uint16_t Bms_Cellmon_ReadAux01(void)
{
    uint16_t raw = g_bms_cellmon_inputs[3];
    uint16_t out = bms_cellmon_scale(raw);
    g_bms_cellmon_state.raw = raw;
    return out;
}

/* REQ-BMS-CEL4 */
uint16_t Bms_Cellmon_ReadAux02(void)
{
    uint16_t raw = g_bms_cellmon_inputs[4];
    uint16_t out = bms_cellmon_scale(raw);
    g_bms_cellmon_state.raw = raw;
    return out;
}

/* REQ-BMS-CEL4 */
uint16_t Bms_Cellmon_ReadAux03(void)
{
    uint16_t raw = g_bms_cellmon_inputs[5];
    uint16_t out = bms_cellmon_scale(raw);
    g_bms_cellmon_state.raw = raw;
    return out;
}

/* REQ-BMS-CEL5 */
uint16_t Bms_Cellmon_Compute(void)
{
    uint16_t a = Bms_Cellmon_ReadCellMv();
    uint16_t b = bms_cellmon_lpf(a, g_bms_cellmon_state.value);
    uint16_t c = bms_cellmon_clamp_u16(b, g_bms_cellmon_cfg.over_volt_mv);
    g_bms_cellmon_state.value = c;
    return c;
}

/* REQ-BMS-CEL6 */
uint8_t Bms_Cellmon_SelfTest(void)
{
    uint8_t crc = bms_cellmon_crc8((const uint8_t *)&g_bms_cellmon_cfg, (uint8_t)sizeof(Bms_Cellmon_Config_t));
    g_bms_cellmon_state.valid = (crc != 0u) ? 1u : 0u;
    return g_bms_cellmon_state.valid;
}

/* REQ-BMS-CEL7 */
void Bms_Cellmon_Step(void)
{
    g_bms_cellmon_state.phase = BMS_CELLMON_P_RUN;
    (void)Bms_Cellmon_Compute();
    if (g_bms_cellmon_state.value > g_bms_cellmon_cfg.over_volt_mv) {
        g_bms_cellmon_state.fault_count++;
        g_bms_cellmon_state.phase = BMS_CELLMON_P_FAULT;
    }
    if (Bms_Cellmon_SelfTest() == 0u) {
        g_bms_cellmon_state.phase = BMS_CELLMON_P_LIMP;
    }
    g_bms_cellmon_state.uptime_ticks++;
}

/* REQ-BMS-CEL1 */
const Bms_Cellmon_State_t *Bms_Cellmon_GetState(void)
{
    return &g_bms_cellmon_state;
}
