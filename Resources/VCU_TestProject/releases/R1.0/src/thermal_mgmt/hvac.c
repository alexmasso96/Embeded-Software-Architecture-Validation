#include "vcu_all.h"

/* ============================================================
 * ThermalMgmt :: hvac   (release R1.0)
 * Thermal Management: coolant loops, HVAC, pump and fan control.
 * ============================================================ */

static Thm_Hvac_Config_t g_thm_hvac_cfg;
static Thm_Hvac_State_t g_thm_hvac_state;
static uint16_t g_thm_hvac_inputs[8];

static uint16_t thm_hvac_clamp_u16(uint16_t v, uint16_t hi);
static uint16_t thm_hvac_scale(uint16_t raw);
static uint16_t thm_hvac_lpf(uint16_t x, uint16_t prev);
static uint8_t thm_hvac_crc8(const uint8_t *p, uint8_t n);
static void thm_hvac_reset(void);

static uint16_t thm_hvac_clamp_u16(uint16_t v, uint16_t hi)
{
    return (v > hi) ? hi : v;
}

static uint16_t thm_hvac_scale(uint16_t raw)
{
    uint32_t s = ((uint32_t)raw * 1000u) >> 10;
    return (uint16_t)(s & 0xFFFFu);
}

static uint16_t thm_hvac_lpf(uint16_t x, uint16_t prev)
{
    /* first-order IIR low-pass: y = (3*prev + x) / 4 */
    return (uint16_t)(((uint32_t)prev * 3u + x) >> 2);
}

static uint8_t thm_hvac_crc8(const uint8_t *p, uint8_t n)
{
    uint8_t crc = 0xFFu;
    uint8_t i;
    for (i = 0u; i < n; i++) {
        crc = (uint8_t)(crc ^ p[i]);
        crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1Du : 0u));
    }
    return crc;
}

static void thm_hvac_reset(void)
{
    g_thm_hvac_state.value = 0u;
    g_thm_hvac_state.raw = 0u;
}

/* REQ-THM-HVA2 */
void Thm_Hvac_Init(const Thm_Hvac_Config_t *cfg)
{
    if (cfg != 0) {
        g_thm_hvac_cfg = *cfg;
    }
    g_thm_hvac_state.phase = THM_HVAC_P_INIT;
    g_thm_hvac_state.valid = 1u;
    /* no fault counter pre-R2.0 */
    thm_hvac_reset();
}

/* REQ-THM-HVA3 */
uint16_t Thm_Hvac_GetCabinTargetC(void)
{
    return g_thm_hvac_cfg.cabin_target_c;
}

/* REQ-THM-HVA3 */
void Thm_Hvac_SetCabinTargetC(uint16_t v)
{
    g_thm_hvac_cfg.cabin_target_c = thm_hvac_clamp_u16(v, 0xFFFFu);
}

/* REQ-THM-HVA3 */
uint16_t Thm_Hvac_GetBlowerMax(void)
{
    return g_thm_hvac_cfg.blower_max;
}

/* REQ-THM-HVA3 */
void Thm_Hvac_SetBlowerMax(uint16_t v)
{
    g_thm_hvac_cfg.blower_max = thm_hvac_clamp_u16(v, 0xFFFFu);
}

/* REQ-THM-HVA4 */
uint16_t Thm_Hvac_ReadCabinC(void)
{
    uint16_t raw = g_thm_hvac_inputs[0];
    uint16_t out = thm_hvac_scale(raw);
    g_thm_hvac_state.raw = raw;
    return out;
}

/* REQ-THM-HVA4 */
uint16_t Thm_Hvac_ReadEvapC(void)
{
    uint16_t raw = g_thm_hvac_inputs[1];
    uint16_t out = thm_hvac_scale(raw);
    g_thm_hvac_state.raw = raw;
    return out;
}

/* REQ-THM-HVA4 */
uint16_t Thm_Hvac_ReadSolarLux(void)
{
    uint16_t raw = g_thm_hvac_inputs[2];
    uint16_t out = thm_hvac_scale(raw);
    g_thm_hvac_state.raw = raw;
    return out;
}

/* REQ-THM-HVA5 */
uint16_t Thm_Hvac_Compute(void)
{
    uint16_t a = Thm_Hvac_ReadCabinC();
    uint16_t b = thm_hvac_lpf(a, g_thm_hvac_state.value);
    uint16_t c = thm_hvac_clamp_u16(b, g_thm_hvac_cfg.cabin_target_c);
    g_thm_hvac_state.value = c;
    return c;
}

/* REQ-THM-HVA9 */
void Thm_Hvac_LegacyReset(void)
{
    /* REQ-THM-HVA9: deprecated legacy reset, removed in R2.0. */
    g_thm_hvac_state.phase = THM_HVAC_P_OFF;
}

/* REQ-THM-HVA7 */
void Thm_Hvac_Step(void)
{
    g_thm_hvac_state.phase = THM_HVAC_P_RUN;
    (void)Thm_Hvac_Compute();
}

/* REQ-THM-HVA1 */
const Thm_Hvac_State_t *Thm_Hvac_GetState(void)
{
    return &g_thm_hvac_state;
}
