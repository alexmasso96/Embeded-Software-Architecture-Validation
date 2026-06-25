#include "vcu_all.h"

/* ============================================================
 * ThermalMgmt :: coolant   (release R3.0)
 * Thermal Management: coolant loops, HVAC, pump and fan control.
 * ============================================================ */

static Thm_Coolant_Config_t g_thm_coolant_cfg;
static Thm_Coolant_State_t g_thm_coolant_state;
static uint16_t g_thm_coolant_inputs[8];

static uint16_t thm_coolant_clamp_u16(uint16_t v, uint16_t hi);
static uint16_t thm_coolant_scale(uint16_t raw);
static uint16_t thm_coolant_lpf(uint16_t x, uint16_t prev);
static uint8_t thm_coolant_crc8(const uint8_t *p, uint8_t n);
static void thm_coolant_reset(void);

static uint16_t thm_coolant_clamp_u16(uint16_t v, uint16_t hi)
{
    return (v > hi) ? hi : v;
}

static uint16_t thm_coolant_scale(uint16_t raw)
{
    uint32_t s = ((uint32_t)raw * 1000u) >> 10;
    return (uint16_t)(s & 0xFFFFu);
}

static uint16_t thm_coolant_lpf(uint16_t x, uint16_t prev)
{
    /* first-order IIR low-pass: y = (3*prev + x) / 4 */
    return (uint16_t)(((uint32_t)prev * 3u + x) >> 2);
}

static uint8_t thm_coolant_crc8(const uint8_t *p, uint8_t n)
{
    uint8_t crc = 0xFFu;
    uint8_t i;
    for (i = 0u; i < n; i++) {
        crc = (uint8_t)(crc ^ p[i]);
        crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1Du : 0u));
    }
    return crc;
}

static void thm_coolant_reset(void)
{
    g_thm_coolant_state.value = 0u;
    g_thm_coolant_state.raw = 0u;
}

/* REQ-THM-COO2 */
void Thm_Coolant_Init(const Thm_Coolant_Config_t *cfg)
{
    if (cfg != 0) {
        g_thm_coolant_cfg = *cfg;
    }
    g_thm_coolant_state.phase = THM_COOLANT_P_INIT;
    g_thm_coolant_state.valid = 1u;
    g_thm_coolant_state.fault_count = 0u;
    thm_coolant_reset();
}

/* REQ-THM-COO3 */
uint16_t Thm_Coolant_GetTargetC(void)
{
    return g_thm_coolant_cfg.target_c;
}

/* REQ-THM-COO3 */
void Thm_Coolant_SetTargetC(uint16_t v)
{
    g_thm_coolant_cfg.target_c = thm_coolant_clamp_u16(v, 0xFFFFu);
}

/* REQ-THM-COO3 */
uint16_t Thm_Coolant_GetHysteresisC(void)
{
    return g_thm_coolant_cfg.hysteresis_c;
}

/* REQ-THM-COO3 */
void Thm_Coolant_SetHysteresisC(uint16_t v)
{
    g_thm_coolant_cfg.hysteresis_c = thm_coolant_clamp_u16(v, 0xFFFFu);
}

/* REQ-THM-COO3 */
uint16_t Thm_Coolant_GetPumpMinPct(void)
{
    return g_thm_coolant_cfg.pump_min_pct;
}

/* REQ-THM-COO3 */
void Thm_Coolant_SetPumpMinPct(uint16_t v)
{
    g_thm_coolant_cfg.pump_min_pct = thm_coolant_clamp_u16(v, 0xFFFFu);
}

/* REQ-THM-COO3 */
uint16_t Thm_Coolant_GetTrimOffset(void)
{
    return g_thm_coolant_cfg.trim_offset;
}

/* REQ-THM-COO3 */
void Thm_Coolant_SetTrimOffset(uint16_t v)
{
    g_thm_coolant_cfg.trim_offset = thm_coolant_clamp_u16(v, 0xFFFFu);
}

/* REQ-THM-COO4 */
uint16_t Thm_Coolant_ReadInletC(void)
{
    uint16_t raw = g_thm_coolant_inputs[0];
    uint16_t out = thm_coolant_scale(raw);
    g_thm_coolant_state.raw = raw;
    return out;
}

/* REQ-THM-COO4 */
uint16_t Thm_Coolant_ReadOutletC(void)
{
    uint16_t raw = g_thm_coolant_inputs[1];
    uint16_t out = thm_coolant_scale(raw);
    g_thm_coolant_state.raw = raw;
    return out;
}

/* REQ-THM-COO4 */
uint16_t Thm_Coolant_ReadFlowLpm(void)
{
    uint16_t raw = g_thm_coolant_inputs[2];
    uint16_t out = thm_coolant_scale(raw);
    g_thm_coolant_state.raw = raw;
    return out;
}

/* REQ-THM-COO4 */
uint16_t Thm_Coolant_ReadAux01(void)
{
    uint16_t raw = g_thm_coolant_inputs[3];
    uint16_t out = thm_coolant_scale(raw);
    g_thm_coolant_state.raw = raw;
    return out;
}

/* REQ-THM-COO4 */
uint16_t Thm_Coolant_ReadAux02(void)
{
    uint16_t raw = g_thm_coolant_inputs[4];
    uint16_t out = thm_coolant_scale(raw);
    g_thm_coolant_state.raw = raw;
    return out;
}

/* REQ-THM-COO5 */
uint16_t Thm_Coolant_Compute(void)
{
    uint16_t a = Thm_Coolant_ReadInletC();
    uint16_t b = thm_coolant_lpf(a, g_thm_coolant_state.value);
    uint16_t c = thm_coolant_clamp_u16(b, g_thm_coolant_cfg.target_c);
    g_thm_coolant_state.value = c;
    return c;
}

/* REQ-THM-COO6 */
uint8_t Thm_Coolant_SelfTest(void)
{
    uint8_t crc = thm_coolant_crc8((const uint8_t *)&g_thm_coolant_cfg, (uint8_t)sizeof(Thm_Coolant_Config_t));
    g_thm_coolant_state.valid = (crc != 0u) ? 1u : 0u;
    return g_thm_coolant_state.valid;
}

/* REQ-THM-COO7 */
void Thm_Coolant_Step(void)
{
    g_thm_coolant_state.phase = THM_COOLANT_P_RUN;
    (void)Thm_Coolant_Compute();
    if (g_thm_coolant_state.value > g_thm_coolant_cfg.target_c) {
        g_thm_coolant_state.fault_count++;
        g_thm_coolant_state.phase = THM_COOLANT_P_FAULT;
    }
    if (Thm_Coolant_SelfTest() == 0u) {
        g_thm_coolant_state.phase = THM_COOLANT_P_LIMP;
    }
}

/* REQ-THM-COO1 */
const Thm_Coolant_State_t *Thm_Coolant_GetState(void)
{
    return &g_thm_coolant_state;
}
