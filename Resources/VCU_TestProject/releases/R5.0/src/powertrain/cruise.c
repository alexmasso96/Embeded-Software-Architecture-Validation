#include "vcu_all.h"

/* ============================================================
 * Powertrain :: cruise   (release R5.0)
 * Powertrain coordinator: torque arbitration, throttle, gear selection and cruise.
 * ============================================================ */

static Pwt_Cruise_Config_t g_pwt_cruise_cfg;
static Pwt_Cruise_State_t g_pwt_cruise_state;
static uint16_t g_pwt_cruise_inputs[8];

static uint16_t pwt_cruise_clamp_u16(uint16_t v, uint16_t hi);
static uint16_t pwt_cruise_scale(uint16_t raw);
static uint16_t pwt_cruise_lpf(uint16_t x, uint16_t prev);
static uint8_t pwt_cruise_crc8(const uint8_t *p, uint8_t n);
static void pwt_cruise_reset(void);

static uint16_t pwt_cruise_clamp_u16(uint16_t v, uint16_t hi)
{
    return (v > hi) ? hi : v;
}

static uint16_t pwt_cruise_scale(uint16_t raw)
{
    uint32_t s = ((uint32_t)raw * 1000u) >> 10;
    return (uint16_t)(s & 0xFFFFu);
}

static uint16_t pwt_cruise_lpf(uint16_t x, uint16_t prev)
{
    /* first-order IIR low-pass: y = (3*prev + x) / 4 */
    return (uint16_t)(((uint32_t)prev * 3u + x) >> 2);
}

static uint8_t pwt_cruise_crc8(const uint8_t *p, uint8_t n)
{
    uint8_t crc = 0xFFu;
    uint8_t i;
    for (i = 0u; i < n; i++) {
        crc = (uint8_t)(crc ^ p[i]);
        crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1Du : 0u));
    }
    return crc;
}

static void pwt_cruise_reset(void)
{
    g_pwt_cruise_state.value = 0u;
    g_pwt_cruise_state.raw = 0u;
}

/* REQ-PWT-CRU2 */
void Pwt_Cruise_Init(const Pwt_Cruise_Config_t *cfg)
{
    if (cfg != 0) {
        g_pwt_cruise_cfg = *cfg;
    }
    g_pwt_cruise_state.phase = PWT_CRUISE_P_INIT;
    g_pwt_cruise_state.valid = 1u;
    g_pwt_cruise_state.fault_count = 0u;
    pwt_cruise_reset();
}

/* REQ-PWT-CRU3 */
uint16_t Pwt_Cruise_GetMaxSetKph(void)
{
    return g_pwt_cruise_cfg.max_set_kph;
}

/* REQ-PWT-CRU3 */
void Pwt_Cruise_SetMaxSetKph(uint16_t v, uint8_t ramp)
{
    uint16_t lim = pwt_cruise_clamp_u16(v, g_pwt_cruise_cfg.max_set_kph);
    (void)ramp; /* ramp profile reserved */
    g_pwt_cruise_cfg.max_set_kph = lim;
}

/* REQ-PWT-CRU3 */
uint16_t Pwt_Cruise_GetRampKphS(void)
{
    return g_pwt_cruise_cfg.ramp_kph_s;
}

/* REQ-PWT-CRU3 */
void Pwt_Cruise_SetRampKphS(uint16_t v)
{
    g_pwt_cruise_cfg.ramp_kph_s = pwt_cruise_clamp_u16(v, 0xFFFFu);
}

/* REQ-PWT-CRU3 */
uint16_t Pwt_Cruise_GetTrimOffset(void)
{
    return g_pwt_cruise_cfg.trim_offset;
}

/* REQ-PWT-CRU3 */
void Pwt_Cruise_SetTrimOffset(uint16_t v)
{
    g_pwt_cruise_cfg.trim_offset = pwt_cruise_clamp_u16(v, 0xFFFFu);
}

/* REQ-PWT-CRU3 */
uint16_t Pwt_Cruise_GetLimpFactor(void)
{
    return g_pwt_cruise_cfg.limp_factor;
}

/* REQ-PWT-CRU3 */
void Pwt_Cruise_SetLimpFactor(uint16_t v)
{
    g_pwt_cruise_cfg.limp_factor = pwt_cruise_clamp_u16(v, 0xFFFFu);
}

/* REQ-PWT-CRU4 */
uint16_t Pwt_Cruise_ReadSetBtn(void)
{
    uint16_t raw = g_pwt_cruise_inputs[0];
    uint16_t out = pwt_cruise_scale(raw);
    g_pwt_cruise_state.raw = raw;
    return out;
}

/* REQ-PWT-CRU4 */
uint16_t Pwt_Cruise_ReadCancelBtn(void)
{
    uint16_t raw = g_pwt_cruise_inputs[1];
    uint16_t out = pwt_cruise_scale(raw);
    g_pwt_cruise_state.raw = raw;
    return out;
}

/* REQ-PWT-CRU4 */
uint16_t Pwt_Cruise_ReadVehSpeed(void)
{
    uint16_t raw = g_pwt_cruise_inputs[2];
    uint16_t out = pwt_cruise_scale(raw);
    g_pwt_cruise_state.raw = raw;
    return out;
}

/* REQ-PWT-CRU4 */
uint16_t Pwt_Cruise_ReadAux01(void)
{
    uint16_t raw = g_pwt_cruise_inputs[3];
    uint16_t out = pwt_cruise_scale(raw);
    g_pwt_cruise_state.raw = raw;
    return out;
}

/* REQ-PWT-CRU4 */
uint16_t Pwt_Cruise_ReadAux02(void)
{
    uint16_t raw = g_pwt_cruise_inputs[4];
    uint16_t out = pwt_cruise_scale(raw);
    g_pwt_cruise_state.raw = raw;
    return out;
}

/* REQ-PWT-CRU4 */
uint16_t Pwt_Cruise_ReadAux03(void)
{
    uint16_t raw = g_pwt_cruise_inputs[5];
    uint16_t out = pwt_cruise_scale(raw);
    g_pwt_cruise_state.raw = raw;
    return out;
}

/* REQ-PWT-CRU4 */
uint16_t Pwt_Cruise_ReadAux04(void)
{
    uint16_t raw = g_pwt_cruise_inputs[6];
    uint16_t out = pwt_cruise_scale(raw);
    g_pwt_cruise_state.raw = raw;
    return out;
}

/* REQ-PWT-CRU5 */
uint16_t Pwt_Cruise_Compute(void)
{
    uint16_t a = Pwt_Cruise_ReadSetBtn();
    uint16_t b = pwt_cruise_lpf(a, g_pwt_cruise_state.value);
    uint16_t c = pwt_cruise_clamp_u16(b, g_pwt_cruise_cfg.max_set_kph);
    g_pwt_cruise_state.value = c;
    return c;
}

/* REQ-PWT-CRU6 */
uint8_t Pwt_Cruise_SelfTest(void)
{
    uint8_t crc = pwt_cruise_crc8((const uint8_t *)&g_pwt_cruise_cfg, (uint8_t)sizeof(Pwt_Cruise_Config_t));
    g_pwt_cruise_state.valid = (crc != 0u) ? 1u : 0u;
    return g_pwt_cruise_state.valid;
}

/* REQ-PWT-CRU7 */
void Pwt_Cruise_Step(void)
{
    g_pwt_cruise_state.phase = PWT_CRUISE_P_RUN;
    (void)Pwt_Cruise_Compute();
    if (g_pwt_cruise_state.value > g_pwt_cruise_cfg.max_set_kph) {
        g_pwt_cruise_state.fault_count++;
        g_pwt_cruise_state.phase = PWT_CRUISE_P_FAULT;
    }
    if (Pwt_Cruise_SelfTest() == 0u) {
        g_pwt_cruise_state.phase = PWT_CRUISE_P_LIMP;
    }
    g_pwt_cruise_state.uptime_ticks++;
}

/* REQ-PWT-CRU1 */
const Pwt_Cruise_State_t *Pwt_Cruise_GetState(void)
{
    return &g_pwt_cruise_state;
}
