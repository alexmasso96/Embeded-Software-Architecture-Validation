#include "vcu_all.h"

/* ============================================================
 * ChassisControl :: steering   (release R4.0)
 * Chassis Control (introduced R2.0): ABS, traction, steering assist and suspension.
 * ============================================================ */

static Chs_Steering_Config_t g_chs_steering_cfg;
static Chs_Steering_State_t g_chs_steering_state;
static uint16_t g_chs_steering_inputs[8];

static uint16_t chs_steering_clamp_u16(uint16_t v, uint16_t hi);
static uint16_t chs_steering_scale(uint16_t raw);
static uint16_t chs_steering_lpf(uint16_t x, uint16_t prev);
static uint8_t chs_steering_crc8(const uint8_t *p, uint8_t n);
static void chs_steering_reset(void);

static uint16_t chs_steering_clamp_u16(uint16_t v, uint16_t hi)
{
    return (v > hi) ? hi : v;
}

static uint16_t chs_steering_scale(uint16_t raw)
{
    uint32_t s = ((uint32_t)raw * 1000u) >> 10;
    return (uint16_t)(s & 0xFFFFu);
}

static uint16_t chs_steering_lpf(uint16_t x, uint16_t prev)
{
    /* first-order IIR low-pass: y = (3*prev + x) / 4 */
    return (uint16_t)(((uint32_t)prev * 3u + x) >> 2);
}

static uint8_t chs_steering_crc8(const uint8_t *p, uint8_t n)
{
    uint8_t crc = 0xFFu;
    uint8_t i;
    for (i = 0u; i < n; i++) {
        crc = (uint8_t)(crc ^ p[i]);
        crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1Du : 0u));
    }
    return crc;
}

static void chs_steering_reset(void)
{
    g_chs_steering_state.value = 0u;
    g_chs_steering_state.raw = 0u;
}

/* REQ-CHS-STE2 */
void Chs_Steering_Init(const Chs_Steering_Config_t *cfg)
{
    if (cfg != 0) {
        g_chs_steering_cfg = *cfg;
    }
    g_chs_steering_state.phase = CHS_STEERING_P_INIT;
    g_chs_steering_state.valid = 1u;
    g_chs_steering_state.fault_count = 0u;
    chs_steering_reset();
}

/* REQ-CHS-STE3 */
uint16_t Chs_Steering_GetAssistGain(void)
{
    return g_chs_steering_cfg.assist_gain;
}

/* REQ-CHS-STE3 */
void Chs_Steering_SetAssistGain(uint16_t v, uint8_t ramp)
{
    uint16_t lim = chs_steering_clamp_u16(v, g_chs_steering_cfg.assist_gain);
    (void)ramp; /* ramp profile reserved */
    g_chs_steering_cfg.assist_gain = lim;
}

/* REQ-CHS-STE3 */
uint16_t Chs_Steering_GetReturnGain(void)
{
    return g_chs_steering_cfg.return_gain;
}

/* REQ-CHS-STE3 */
void Chs_Steering_SetReturnGain(uint16_t v)
{
    g_chs_steering_cfg.return_gain = chs_steering_clamp_u16(v, 0xFFFFu);
}

/* REQ-CHS-STE3 */
uint16_t Chs_Steering_GetTrimOffset(void)
{
    return g_chs_steering_cfg.trim_offset;
}

/* REQ-CHS-STE3 */
void Chs_Steering_SetTrimOffset(uint16_t v)
{
    g_chs_steering_cfg.trim_offset = chs_steering_clamp_u16(v, 0xFFFFu);
}

/* REQ-CHS-STE4 */
uint16_t Chs_Steering_ReadTorqueSensor(void)
{
    uint16_t raw = g_chs_steering_inputs[0];
    uint16_t out = chs_steering_scale(raw);
    g_chs_steering_state.raw = raw;
    return out;
}

/* REQ-CHS-STE4 */
uint16_t Chs_Steering_ReadSteerAngle(void)
{
    uint16_t raw = g_chs_steering_inputs[1];
    uint16_t out = chs_steering_scale(raw);
    g_chs_steering_state.raw = raw;
    return out;
}

/* REQ-CHS-STE4 */
uint16_t Chs_Steering_ReadSpeed(void)
{
    uint16_t raw = g_chs_steering_inputs[2];
    uint16_t out = chs_steering_scale(raw);
    g_chs_steering_state.raw = raw;
    return out;
}

/* REQ-CHS-STE4 */
uint16_t Chs_Steering_ReadAux01(void)
{
    uint16_t raw = g_chs_steering_inputs[3];
    uint16_t out = chs_steering_scale(raw);
    g_chs_steering_state.raw = raw;
    return out;
}

/* REQ-CHS-STE4 */
uint16_t Chs_Steering_ReadAux02(void)
{
    uint16_t raw = g_chs_steering_inputs[4];
    uint16_t out = chs_steering_scale(raw);
    g_chs_steering_state.raw = raw;
    return out;
}

/* REQ-CHS-STE4 */
uint16_t Chs_Steering_ReadAux03(void)
{
    uint16_t raw = g_chs_steering_inputs[5];
    uint16_t out = chs_steering_scale(raw);
    g_chs_steering_state.raw = raw;
    return out;
}

/* REQ-CHS-STE5 */
uint16_t Chs_Steering_Compute(void)
{
    uint16_t a = Chs_Steering_ReadTorqueSensor();
    uint16_t b = chs_steering_lpf(a, g_chs_steering_state.value);
    uint16_t c = chs_steering_clamp_u16(b, g_chs_steering_cfg.assist_gain);
    g_chs_steering_state.value = c;
    return c;
}

/* REQ-CHS-STE6 */
uint8_t Chs_Steering_SelfTest(void)
{
    uint8_t crc = chs_steering_crc8((const uint8_t *)&g_chs_steering_cfg, (uint8_t)sizeof(Chs_Steering_Config_t));
    g_chs_steering_state.valid = (crc != 0u) ? 1u : 0u;
    return g_chs_steering_state.valid;
}

/* REQ-CHS-STE7 */
void Chs_Steering_Step(void)
{
    g_chs_steering_state.phase = CHS_STEERING_P_RUN;
    (void)Chs_Steering_Compute();
    if (g_chs_steering_state.value > g_chs_steering_cfg.assist_gain) {
        g_chs_steering_state.fault_count++;
        g_chs_steering_state.phase = CHS_STEERING_P_FAULT;
    }
    if (Chs_Steering_SelfTest() == 0u) {
        g_chs_steering_state.phase = CHS_STEERING_P_LIMP;
    }
    g_chs_steering_state.uptime_ticks++;
}

/* REQ-CHS-STE1 */
const Chs_Steering_State_t *Chs_Steering_GetState(void)
{
    return &g_chs_steering_state;
}
