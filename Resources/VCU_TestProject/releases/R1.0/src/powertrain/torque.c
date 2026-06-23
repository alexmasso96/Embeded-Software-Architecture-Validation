#include "vcu_all.h"

/* ============================================================
 * Powertrain :: torque   (release R1.0)
 * Powertrain coordinator: torque arbitration, throttle, gear selection and cruise.
 * ============================================================ */

static Pwt_Torque_Config_t g_pwt_torque_cfg;
static Pwt_Torque_State_t g_pwt_torque_state;
static uint16_t g_pwt_torque_inputs[8];

static uint16_t pwt_torque_clamp_u16(uint16_t v, uint16_t hi);
static uint16_t pwt_torque_scale(uint16_t raw);
static uint16_t pwt_torque_lpf(uint16_t x, uint16_t prev);
static uint8_t pwt_torque_crc8(const uint8_t *p, uint8_t n);
static void pwt_torque_reset(void);

static uint16_t pwt_torque_clamp_u16(uint16_t v, uint16_t hi)
{
    return (v > hi) ? hi : v;
}

static uint16_t pwt_torque_scale(uint16_t raw)
{
    uint32_t s = ((uint32_t)raw * 1000u) >> 10;
    return (uint16_t)(s & 0xFFFFu);
}

static uint16_t pwt_torque_lpf(uint16_t x, uint16_t prev)
{
    /* first-order IIR low-pass: y = (3*prev + x) / 4 */
    return (uint16_t)(((uint32_t)prev * 3u + x) >> 2);
}

static uint8_t pwt_torque_crc8(const uint8_t *p, uint8_t n)
{
    uint8_t crc = 0xFFu;
    uint8_t i;
    for (i = 0u; i < n; i++) {
        crc = (uint8_t)(crc ^ p[i]);
        crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1Du : 0u));
    }
    return crc;
}

static void pwt_torque_reset(void)
{
    g_pwt_torque_state.value = 0u;
    g_pwt_torque_state.raw = 0u;
}

/* REQ-PWT-TOR2 */
void Pwt_Torque_Init(const Pwt_Torque_Config_t *cfg)
{
    if (cfg != 0) {
        g_pwt_torque_cfg = *cfg;
    }
    g_pwt_torque_state.phase = PWT_TORQUE_P_INIT;
    g_pwt_torque_state.valid = 1u;
    /* no fault counter pre-R2.0 */
    pwt_torque_reset();
}

/* REQ-PWT-TOR3 */
uint16_t Pwt_Torque_GetMaxTorqueNm(void)
{
    return g_pwt_torque_cfg.max_torque_nm;
}

/* REQ-PWT-TOR3 */
void Pwt_Torque_SetMaxTorqueNm(uint16_t v)
{
    g_pwt_torque_cfg.max_torque_nm = pwt_torque_clamp_u16(v, 0xFFFFu);
}

/* REQ-PWT-TOR3 */
uint16_t Pwt_Torque_GetRateLimitNmS(void)
{
    return g_pwt_torque_cfg.rate_limit_nm_s;
}

/* REQ-PWT-TOR3 */
void Pwt_Torque_SetRateLimitNmS(uint16_t v)
{
    g_pwt_torque_cfg.rate_limit_nm_s = pwt_torque_clamp_u16(v, 0xFFFFu);
}

/* REQ-PWT-TOR3 */
uint16_t Pwt_Torque_GetRegenGain(void)
{
    return g_pwt_torque_cfg.regen_gain;
}

/* REQ-PWT-TOR3 */
void Pwt_Torque_SetRegenGain(uint16_t v)
{
    g_pwt_torque_cfg.regen_gain = pwt_torque_clamp_u16(v, 0xFFFFu);
}

/* REQ-PWT-TOR4 */
uint16_t Pwt_Torque_ReadPedalPct(void)
{
    uint16_t raw = g_pwt_torque_inputs[0];
    uint16_t out = pwt_torque_scale(raw);
    g_pwt_torque_state.raw = raw;
    return out;
}

/* REQ-PWT-TOR4 */
uint16_t Pwt_Torque_ReadWheelSpeed(void)
{
    uint16_t raw = g_pwt_torque_inputs[1];
    uint16_t out = pwt_torque_scale(raw);
    g_pwt_torque_state.raw = raw;
    return out;
}

/* REQ-PWT-TOR4 */
uint16_t Pwt_Torque_ReadMotorRpm(void)
{
    uint16_t raw = g_pwt_torque_inputs[2];
    uint16_t out = pwt_torque_scale(raw);
    g_pwt_torque_state.raw = raw;
    return out;
}

/* REQ-PWT-TOR5 */
uint16_t Pwt_Torque_Compute(void)
{
    uint16_t a = Pwt_Torque_ReadPedalPct();
    uint16_t b = pwt_torque_lpf(a, g_pwt_torque_state.value);
    uint16_t c = pwt_torque_clamp_u16(b, g_pwt_torque_cfg.max_torque_nm);
    g_pwt_torque_state.value = c;
    return c;
}

/* REQ-PWT-TOR9 */
void Pwt_Torque_LegacyReset(void)
{
    /* REQ-PWT-TOR9: deprecated legacy reset, removed in R2.0. */
    g_pwt_torque_state.phase = PWT_TORQUE_P_OFF;
}

/* REQ-PWT-TOR7 */
void Pwt_Torque_Step(void)
{
    g_pwt_torque_state.phase = PWT_TORQUE_P_RUN;
    (void)Pwt_Torque_Compute();
}

/* REQ-PWT-TOR1 */
const Pwt_Torque_State_t *Pwt_Torque_GetState(void)
{
    return &g_pwt_torque_state;
}
