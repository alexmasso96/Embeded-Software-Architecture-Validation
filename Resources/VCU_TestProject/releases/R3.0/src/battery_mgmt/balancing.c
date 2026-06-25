#include "vcu_all.h"

/* ============================================================
 * BatteryMgmt :: balancing   (release R3.0)
 * Battery Management System: cell monitoring, state of charge, balancing and contactor control.
 * ============================================================ */

static Bms_Balancing_Config_t g_bms_balancing_cfg;
static Bms_Balancing_State_t g_bms_balancing_state;
static uint16_t g_bms_balancing_inputs[8];

static uint16_t bms_balancing_clamp_u16(uint16_t v, uint16_t hi);
static uint16_t bms_balancing_scale(uint16_t raw);
static uint16_t bms_balancing_lpf(uint16_t x, uint16_t prev);
static uint8_t bms_balancing_crc8(const uint8_t *p, uint8_t n);
static void bms_balancing_reset(void);

static uint16_t bms_balancing_clamp_u16(uint16_t v, uint16_t hi)
{
    return (v > hi) ? hi : v;
}

static uint16_t bms_balancing_scale(uint16_t raw)
{
    uint32_t s = ((uint32_t)raw * 1000u) >> 10;
    return (uint16_t)(s & 0xFFFFu);
}

static uint16_t bms_balancing_lpf(uint16_t x, uint16_t prev)
{
    /* first-order IIR low-pass: y = (3*prev + x) / 4 */
    return (uint16_t)(((uint32_t)prev * 3u + x) >> 2);
}

static uint8_t bms_balancing_crc8(const uint8_t *p, uint8_t n)
{
    uint8_t crc = 0xFFu;
    uint8_t i;
    for (i = 0u; i < n; i++) {
        crc = (uint8_t)(crc ^ p[i]);
        crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1Du : 0u));
    }
    return crc;
}

static void bms_balancing_reset(void)
{
    g_bms_balancing_state.value = 0u;
    g_bms_balancing_state.raw = 0u;
}

/* REQ-BMS-BAL2 */
void Bms_Balancing_Init(const Bms_Balancing_Config_t *cfg)
{
    if (cfg != 0) {
        g_bms_balancing_cfg = *cfg;
    }
    g_bms_balancing_state.phase = BMS_BALANCING_P_INIT;
    g_bms_balancing_state.valid = 1u;
    g_bms_balancing_state.fault_count = 0u;
    bms_balancing_reset();
}

/* REQ-BMS-BAL3 */
uint16_t Bms_Balancing_GetBalanceDeltaMv(void)
{
    return g_bms_balancing_cfg.balance_delta_mv;
}

/* REQ-BMS-BAL3 */
void Bms_Balancing_SetBalanceDeltaMv(uint16_t v)
{
    g_bms_balancing_cfg.balance_delta_mv = bms_balancing_clamp_u16(v, 0xFFFFu);
}

/* REQ-BMS-BAL3 */
uint16_t Bms_Balancing_GetBalanceMs(void)
{
    return g_bms_balancing_cfg.balance_ms;
}

/* REQ-BMS-BAL3 */
void Bms_Balancing_SetBalanceMs(uint16_t v)
{
    g_bms_balancing_cfg.balance_ms = bms_balancing_clamp_u16(v, 0xFFFFu);
}

/* REQ-BMS-BAL3 */
uint16_t Bms_Balancing_GetTrimOffset(void)
{
    return g_bms_balancing_cfg.trim_offset;
}

/* REQ-BMS-BAL3 */
void Bms_Balancing_SetTrimOffset(uint16_t v)
{
    g_bms_balancing_cfg.trim_offset = bms_balancing_clamp_u16(v, 0xFFFFu);
}

/* REQ-BMS-BAL4 */
uint16_t Bms_Balancing_ReadMaxCellMv(void)
{
    uint16_t raw = g_bms_balancing_inputs[0];
    uint16_t out = bms_balancing_scale(raw);
    g_bms_balancing_state.raw = raw;
    return out;
}

/* REQ-BMS-BAL4 */
uint16_t Bms_Balancing_ReadMinCellMv(void)
{
    uint16_t raw = g_bms_balancing_inputs[1];
    uint16_t out = bms_balancing_scale(raw);
    g_bms_balancing_state.raw = raw;
    return out;
}

/* REQ-BMS-BAL4 */
uint16_t Bms_Balancing_ReadAux01(void)
{
    uint16_t raw = g_bms_balancing_inputs[2];
    uint16_t out = bms_balancing_scale(raw);
    g_bms_balancing_state.raw = raw;
    return out;
}

/* REQ-BMS-BAL4 */
uint16_t Bms_Balancing_ReadAux02(void)
{
    uint16_t raw = g_bms_balancing_inputs[3];
    uint16_t out = bms_balancing_scale(raw);
    g_bms_balancing_state.raw = raw;
    return out;
}

/* REQ-BMS-BAL5 */
uint16_t Bms_Balancing_Compute(void)
{
    uint16_t a = Bms_Balancing_ReadMaxCellMv();
    uint16_t b = bms_balancing_lpf(a, g_bms_balancing_state.value);
    uint16_t c = bms_balancing_clamp_u16(b, g_bms_balancing_cfg.balance_delta_mv);
    g_bms_balancing_state.value = c;
    return c;
}

/* REQ-BMS-BAL6 */
uint8_t Bms_Balancing_SelfTest(void)
{
    uint8_t crc = bms_balancing_crc8((const uint8_t *)&g_bms_balancing_cfg, (uint8_t)sizeof(Bms_Balancing_Config_t));
    g_bms_balancing_state.valid = (crc != 0u) ? 1u : 0u;
    return g_bms_balancing_state.valid;
}

/* REQ-BMS-BAL7 */
void Bms_Balancing_Step(void)
{
    g_bms_balancing_state.phase = BMS_BALANCING_P_RUN;
    (void)Bms_Balancing_Compute();
    if (g_bms_balancing_state.value > g_bms_balancing_cfg.balance_delta_mv) {
        g_bms_balancing_state.fault_count++;
        g_bms_balancing_state.phase = BMS_BALANCING_P_FAULT;
    }
    if (Bms_Balancing_SelfTest() == 0u) {
        g_bms_balancing_state.phase = BMS_BALANCING_P_LIMP;
    }
}

/* REQ-BMS-BAL1 */
const Bms_Balancing_State_t *Bms_Balancing_GetState(void)
{
    return &g_bms_balancing_state;
}
