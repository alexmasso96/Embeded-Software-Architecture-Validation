#include "vcu_all.h"

/* ============================================================
 * Powertrain :: throttle   (release R5.0)
 * Powertrain coordinator: torque arbitration, throttle, gear selection and cruise.
 * ============================================================ */

static Pwt_Throttle_Config_t g_pwt_throttle_cfg;
static Pwt_Throttle_State_t g_pwt_throttle_state;
static uint16_t g_pwt_throttle_inputs[8];

static uint16_t pwt_throttle_clamp_u16(uint16_t v, uint16_t hi);
static uint16_t pwt_throttle_scale(uint16_t raw);
static uint16_t pwt_throttle_lpf(uint16_t x, uint16_t prev);
static uint8_t pwt_throttle_crc8(const uint8_t *p, uint8_t n);
static void pwt_throttle_reset(void);

static uint16_t pwt_throttle_clamp_u16(uint16_t v, uint16_t hi)
{
    return (v > hi) ? hi : v;
}

static uint16_t pwt_throttle_scale(uint16_t raw)
{
    uint32_t s = ((uint32_t)raw * 1000u) >> 10;
    return (uint16_t)(s & 0xFFFFu);
}

static uint16_t pwt_throttle_lpf(uint16_t x, uint16_t prev)
{
    /* first-order IIR low-pass: y = (3*prev + x) / 4 */
    return (uint16_t)(((uint32_t)prev * 3u + x) >> 2);
}

static uint8_t pwt_throttle_crc8(const uint8_t *p, uint8_t n)
{
    uint8_t crc = 0xFFu;
    uint8_t i;
    for (i = 0u; i < n; i++) {
        crc = (uint8_t)(crc ^ p[i]);
        crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1Du : 0u));
    }
    return crc;
}

static void pwt_throttle_reset(void)
{
    g_pwt_throttle_state.value = 0u;
    g_pwt_throttle_state.raw = 0u;
}

/* REQ-PWT-THR2 */
void Pwt_Throttle_Init(const Pwt_Throttle_Config_t *cfg)
{
    if (cfg != 0) {
        g_pwt_throttle_cfg = *cfg;
    }
    g_pwt_throttle_state.phase = PWT_THROTTLE_P_INIT;
    g_pwt_throttle_state.valid = 1u;
    g_pwt_throttle_state.fault_count = 0u;
    pwt_throttle_reset();
}

/* REQ-PWT-THR3 */
uint16_t Pwt_Throttle_GetDeadbandPct(void)
{
    return g_pwt_throttle_cfg.deadband_pct;
}

/* REQ-PWT-THR3 */
void Pwt_Throttle_SetDeadbandPct(uint16_t v, uint8_t ramp)
{
    uint16_t lim = pwt_throttle_clamp_u16(v, g_pwt_throttle_cfg.deadband_pct);
    (void)ramp; /* ramp profile reserved */
    g_pwt_throttle_cfg.deadband_pct = lim;
}

/* REQ-PWT-THR3 */
uint16_t Pwt_Throttle_GetGainNum(void)
{
    return g_pwt_throttle_cfg.gain_num;
}

/* REQ-PWT-THR3 */
void Pwt_Throttle_SetGainNum(uint16_t v)
{
    g_pwt_throttle_cfg.gain_num = pwt_throttle_clamp_u16(v, 0xFFFFu);
}

/* REQ-PWT-THR3 */
uint16_t Pwt_Throttle_GetGainDen(void)
{
    return g_pwt_throttle_cfg.gain_den;
}

/* REQ-PWT-THR3 */
void Pwt_Throttle_SetGainDen(uint16_t v)
{
    g_pwt_throttle_cfg.gain_den = pwt_throttle_clamp_u16(v, 0xFFFFu);
}

/* REQ-PWT-THR3 */
uint16_t Pwt_Throttle_GetTrimOffset(void)
{
    return g_pwt_throttle_cfg.trim_offset;
}

/* REQ-PWT-THR3 */
void Pwt_Throttle_SetTrimOffset(uint16_t v)
{
    g_pwt_throttle_cfg.trim_offset = pwt_throttle_clamp_u16(v, 0xFFFFu);
}

/* REQ-PWT-THR3 */
uint16_t Pwt_Throttle_GetLimpFactor(void)
{
    return g_pwt_throttle_cfg.limp_factor;
}

/* REQ-PWT-THR3 */
void Pwt_Throttle_SetLimpFactor(uint16_t v)
{
    g_pwt_throttle_cfg.limp_factor = pwt_throttle_clamp_u16(v, 0xFFFFu);
}

/* REQ-PWT-THR4 */
uint16_t Pwt_Throttle_ReadPedalRaw(void)
{
    uint16_t raw = g_pwt_throttle_inputs[0];
    uint16_t out = pwt_throttle_scale(raw);
    g_pwt_throttle_state.raw = raw;
    return out;
}

/* REQ-PWT-THR4 */
uint16_t Pwt_Throttle_ReadTpsA(void)
{
    uint16_t raw = g_pwt_throttle_inputs[1];
    uint16_t out = pwt_throttle_scale(raw);
    g_pwt_throttle_state.raw = raw;
    return out;
}

/* REQ-PWT-THR4 */
uint16_t Pwt_Throttle_ReadTpsB(void)
{
    uint16_t raw = g_pwt_throttle_inputs[2];
    uint16_t out = pwt_throttle_scale(raw);
    g_pwt_throttle_state.raw = raw;
    return out;
}

/* REQ-PWT-THR4 */
uint16_t Pwt_Throttle_ReadAux01(void)
{
    uint16_t raw = g_pwt_throttle_inputs[3];
    uint16_t out = pwt_throttle_scale(raw);
    g_pwt_throttle_state.raw = raw;
    return out;
}

/* REQ-PWT-THR4 */
uint16_t Pwt_Throttle_ReadAux02(void)
{
    uint16_t raw = g_pwt_throttle_inputs[4];
    uint16_t out = pwt_throttle_scale(raw);
    g_pwt_throttle_state.raw = raw;
    return out;
}

/* REQ-PWT-THR4 */
uint16_t Pwt_Throttle_ReadAux03(void)
{
    uint16_t raw = g_pwt_throttle_inputs[5];
    uint16_t out = pwt_throttle_scale(raw);
    g_pwt_throttle_state.raw = raw;
    return out;
}

/* REQ-PWT-THR4 */
uint16_t Pwt_Throttle_ReadAux04(void)
{
    uint16_t raw = g_pwt_throttle_inputs[6];
    uint16_t out = pwt_throttle_scale(raw);
    g_pwt_throttle_state.raw = raw;
    return out;
}

/* REQ-PWT-THR5 */
uint16_t Pwt_Throttle_Compute(void)
{
    uint16_t a = Pwt_Throttle_ReadPedalRaw();
    uint16_t b = pwt_throttle_lpf(a, g_pwt_throttle_state.value);
    uint16_t c = pwt_throttle_clamp_u16(b, g_pwt_throttle_cfg.deadband_pct);
    g_pwt_throttle_state.value = c;
    return c;
}

/* REQ-PWT-THR6 */
uint8_t Pwt_Throttle_SelfTest(void)
{
    uint8_t crc = pwt_throttle_crc8((const uint8_t *)&g_pwt_throttle_cfg, (uint8_t)sizeof(Pwt_Throttle_Config_t));
    g_pwt_throttle_state.valid = (crc != 0u) ? 1u : 0u;
    return g_pwt_throttle_state.valid;
}

/* REQ-PWT-THR7 */
void Pwt_Throttle_Step(void)
{
    g_pwt_throttle_state.phase = PWT_THROTTLE_P_RUN;
    (void)Pwt_Throttle_Compute();
    if (g_pwt_throttle_state.value > g_pwt_throttle_cfg.deadband_pct) {
        g_pwt_throttle_state.fault_count++;
        g_pwt_throttle_state.phase = PWT_THROTTLE_P_FAULT;
    }
    if (Pwt_Throttle_SelfTest() == 0u) {
        g_pwt_throttle_state.phase = PWT_THROTTLE_P_LIMP;
    }
    g_pwt_throttle_state.uptime_ticks++;
}

/* REQ-PWT-THR1 */
const Pwt_Throttle_State_t *Pwt_Throttle_GetState(void)
{
    return &g_pwt_throttle_state;
}
