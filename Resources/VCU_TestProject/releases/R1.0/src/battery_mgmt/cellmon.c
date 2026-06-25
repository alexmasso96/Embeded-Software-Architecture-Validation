#include "vcu_all.h"

/* ============================================================
 * BatteryMgmt :: cellmon   (release R1.0)
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
    /* no fault counter pre-R2.0 */
    bms_cellmon_reset();
}

/* REQ-BMS-CEL3 */
uint16_t Bms_Cellmon_GetOverVoltMv(void)
{
    return g_bms_cellmon_cfg.over_volt_mv;
}

/* REQ-BMS-CEL3 */
void Bms_Cellmon_SetOverVoltMv(uint16_t v)
{
    g_bms_cellmon_cfg.over_volt_mv = bms_cellmon_clamp_u16(v, 0xFFFFu);
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

/* REQ-BMS-CEL5 */
uint16_t Bms_Cellmon_Compute(void)
{
    uint16_t a = Bms_Cellmon_ReadCellMv();
    uint16_t b = bms_cellmon_lpf(a, g_bms_cellmon_state.value);
    uint16_t c = bms_cellmon_clamp_u16(b, g_bms_cellmon_cfg.over_volt_mv);
    g_bms_cellmon_state.value = c;
    return c;
}

/* REQ-BMS-CEL9 */
void Bms_Cellmon_LegacyReset(void)
{
    /* REQ-BMS-CEL9: deprecated legacy reset, removed in R2.0. */
    g_bms_cellmon_state.phase = BMS_CELLMON_P_OFF;
}

/* REQ-BMS-CEL7 */
void Bms_Cellmon_Step(void)
{
    g_bms_cellmon_state.phase = BMS_CELLMON_P_RUN;
    (void)Bms_Cellmon_Compute();
}

/* REQ-BMS-CEL1 */
const Bms_Cellmon_State_t *Bms_Cellmon_GetState(void)
{
    return &g_bms_cellmon_state;
}
