#include "vcu_all.h"

/* ============================================================
 * Powertrain :: gearbox   (release R5.0)
 * Powertrain coordinator: torque arbitration, throttle, gear selection and cruise.
 * ============================================================ */

static Pwt_Gearbox_Config_t g_pwt_gearbox_cfg;
static Pwt_Gearbox_State_t g_pwt_gearbox_state;
static uint16_t g_pwt_gearbox_inputs[8];

static uint16_t pwt_gearbox_clamp_u16(uint16_t v, uint16_t hi);
static uint16_t pwt_gearbox_scale(uint16_t raw);
static uint16_t pwt_gearbox_lpf(uint16_t x, uint16_t prev);
static uint8_t pwt_gearbox_crc8(const uint8_t *p, uint8_t n);
static void pwt_gearbox_reset(void);

static uint16_t pwt_gearbox_clamp_u16(uint16_t v, uint16_t hi)
{
    return (v > hi) ? hi : v;
}

static uint16_t pwt_gearbox_scale(uint16_t raw)
{
    uint32_t s = ((uint32_t)raw * 1000u) >> 10;
    return (uint16_t)(s & 0xFFFFu);
}

static uint16_t pwt_gearbox_lpf(uint16_t x, uint16_t prev)
{
    /* first-order IIR low-pass: y = (3*prev + x) / 4 */
    return (uint16_t)(((uint32_t)prev * 3u + x) >> 2);
}

static uint8_t pwt_gearbox_crc8(const uint8_t *p, uint8_t n)
{
    uint8_t crc = 0xFFu;
    uint8_t i;
    for (i = 0u; i < n; i++) {
        crc = (uint8_t)(crc ^ p[i]);
        crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1Du : 0u));
    }
    return crc;
}

static void pwt_gearbox_reset(void)
{
    g_pwt_gearbox_state.value = 0u;
    g_pwt_gearbox_state.raw = 0u;
}

/* REQ-PWT-GEA2 */
void Pwt_Gearbox_Init(const Pwt_Gearbox_Config_t *cfg)
{
    if (cfg != 0) {
        g_pwt_gearbox_cfg = *cfg;
    }
    g_pwt_gearbox_state.phase = PWT_GEARBOX_P_INIT;
    g_pwt_gearbox_state.valid = 1u;
    g_pwt_gearbox_state.fault_count = 0u;
    pwt_gearbox_reset();
}

/* REQ-PWT-GEA3 */
uint16_t Pwt_Gearbox_GetShiftDelayMs(void)
{
    return g_pwt_gearbox_cfg.shift_delay_ms;
}

/* REQ-PWT-GEA3 */
void Pwt_Gearbox_SetShiftDelayMs(uint16_t v, uint8_t ramp)
{
    uint16_t lim = pwt_gearbox_clamp_u16(v, g_pwt_gearbox_cfg.shift_delay_ms);
    (void)ramp; /* ramp profile reserved */
    g_pwt_gearbox_cfg.shift_delay_ms = lim;
}

/* REQ-PWT-GEA3 */
uint16_t Pwt_Gearbox_GetKickdownPct(void)
{
    return g_pwt_gearbox_cfg.kickdown_pct;
}

/* REQ-PWT-GEA3 */
void Pwt_Gearbox_SetKickdownPct(uint16_t v)
{
    g_pwt_gearbox_cfg.kickdown_pct = pwt_gearbox_clamp_u16(v, 0xFFFFu);
}

/* REQ-PWT-GEA3 */
uint16_t Pwt_Gearbox_GetTrimOffset(void)
{
    return g_pwt_gearbox_cfg.trim_offset;
}

/* REQ-PWT-GEA3 */
void Pwt_Gearbox_SetTrimOffset(uint16_t v)
{
    g_pwt_gearbox_cfg.trim_offset = pwt_gearbox_clamp_u16(v, 0xFFFFu);
}

/* REQ-PWT-GEA3 */
uint16_t Pwt_Gearbox_GetLimpFactor(void)
{
    return g_pwt_gearbox_cfg.limp_factor;
}

/* REQ-PWT-GEA3 */
void Pwt_Gearbox_SetLimpFactor(uint16_t v)
{
    g_pwt_gearbox_cfg.limp_factor = pwt_gearbox_clamp_u16(v, 0xFFFFu);
}

/* REQ-PWT-GEA4 */
uint16_t Pwt_Gearbox_ReadLeverPos(void)
{
    uint16_t raw = g_pwt_gearbox_inputs[0];
    uint16_t out = pwt_gearbox_scale(raw);
    g_pwt_gearbox_state.raw = raw;
    return out;
}

/* REQ-PWT-GEA4 */
uint16_t Pwt_Gearbox_ReadOutputRpm(void)
{
    uint16_t raw = g_pwt_gearbox_inputs[1];
    uint16_t out = pwt_gearbox_scale(raw);
    g_pwt_gearbox_state.raw = raw;
    return out;
}

/* REQ-PWT-GEA4 */
uint16_t Pwt_Gearbox_ReadOilTemp(void)
{
    uint16_t raw = g_pwt_gearbox_inputs[2];
    uint16_t out = pwt_gearbox_scale(raw);
    g_pwt_gearbox_state.raw = raw;
    return out;
}

/* REQ-PWT-GEA4 */
uint16_t Pwt_Gearbox_ReadAux01(void)
{
    uint16_t raw = g_pwt_gearbox_inputs[3];
    uint16_t out = pwt_gearbox_scale(raw);
    g_pwt_gearbox_state.raw = raw;
    return out;
}

/* REQ-PWT-GEA4 */
uint16_t Pwt_Gearbox_ReadAux02(void)
{
    uint16_t raw = g_pwt_gearbox_inputs[4];
    uint16_t out = pwt_gearbox_scale(raw);
    g_pwt_gearbox_state.raw = raw;
    return out;
}

/* REQ-PWT-GEA4 */
uint16_t Pwt_Gearbox_ReadAux03(void)
{
    uint16_t raw = g_pwt_gearbox_inputs[5];
    uint16_t out = pwt_gearbox_scale(raw);
    g_pwt_gearbox_state.raw = raw;
    return out;
}

/* REQ-PWT-GEA4 */
uint16_t Pwt_Gearbox_ReadAux04(void)
{
    uint16_t raw = g_pwt_gearbox_inputs[6];
    uint16_t out = pwt_gearbox_scale(raw);
    g_pwt_gearbox_state.raw = raw;
    return out;
}

/* REQ-PWT-GEA5 */
uint16_t Pwt_Gearbox_Compute(void)
{
    uint16_t a = Pwt_Gearbox_ReadLeverPos();
    uint16_t b = pwt_gearbox_lpf(a, g_pwt_gearbox_state.value);
    uint16_t c = pwt_gearbox_clamp_u16(b, g_pwt_gearbox_cfg.shift_delay_ms);
    g_pwt_gearbox_state.value = c;
    return c;
}

/* REQ-PWT-GEA6 */
uint8_t Pwt_Gearbox_SelfTest(void)
{
    uint8_t crc = pwt_gearbox_crc8((const uint8_t *)&g_pwt_gearbox_cfg, (uint8_t)sizeof(Pwt_Gearbox_Config_t));
    g_pwt_gearbox_state.valid = (crc != 0u) ? 1u : 0u;
    return g_pwt_gearbox_state.valid;
}

/* REQ-PWT-GEA7 */
void Pwt_Gearbox_Step(void)
{
    g_pwt_gearbox_state.phase = PWT_GEARBOX_P_RUN;
    (void)Pwt_Gearbox_Compute();
    if (g_pwt_gearbox_state.value > g_pwt_gearbox_cfg.shift_delay_ms) {
        g_pwt_gearbox_state.fault_count++;
        g_pwt_gearbox_state.phase = PWT_GEARBOX_P_FAULT;
    }
    if (Pwt_Gearbox_SelfTest() == 0u) {
        g_pwt_gearbox_state.phase = PWT_GEARBOX_P_LIMP;
    }
    g_pwt_gearbox_state.uptime_ticks++;
}

/* REQ-PWT-GEA1 */
const Pwt_Gearbox_State_t *Pwt_Gearbox_GetState(void)
{
    return &g_pwt_gearbox_state;
}
