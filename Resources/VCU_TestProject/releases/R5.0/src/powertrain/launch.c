#include "vcu_all.h"

/* ============================================================
 * Powertrain :: launch   (release R5.0)
 * Powertrain coordinator: torque arbitration, throttle, gear selection and cruise.
 * ============================================================ */

static Pwt_Launch_Config_t g_pwt_launch_cfg;
static Pwt_Launch_State_t g_pwt_launch_state;
static uint16_t g_pwt_launch_inputs[8];

static uint16_t pwt_launch_clamp_u16(uint16_t v, uint16_t hi);
static uint16_t pwt_launch_scale(uint16_t raw);
static uint16_t pwt_launch_lpf(uint16_t x, uint16_t prev);
static uint8_t pwt_launch_crc8(const uint8_t *p, uint8_t n);
static void pwt_launch_reset(void);

static uint16_t pwt_launch_clamp_u16(uint16_t v, uint16_t hi)
{
    return (v > hi) ? hi : v;
}

static uint16_t pwt_launch_scale(uint16_t raw)
{
    uint32_t s = ((uint32_t)raw * 1000u) >> 10;
    return (uint16_t)(s & 0xFFFFu);
}

static uint16_t pwt_launch_lpf(uint16_t x, uint16_t prev)
{
    /* first-order IIR low-pass: y = (3*prev + x) / 4 */
    return (uint16_t)(((uint32_t)prev * 3u + x) >> 2);
}

static uint8_t pwt_launch_crc8(const uint8_t *p, uint8_t n)
{
    uint8_t crc = 0xFFu;
    uint8_t i;
    for (i = 0u; i < n; i++) {
        crc = (uint8_t)(crc ^ p[i]);
        crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1Du : 0u));
    }
    return crc;
}

static void pwt_launch_reset(void)
{
    g_pwt_launch_state.value = 0u;
    g_pwt_launch_state.raw = 0u;
}

/* REQ-PWT-LAU2 */
void Pwt_Launch_Init(const Pwt_Launch_Config_t *cfg)
{
    if (cfg != 0) {
        g_pwt_launch_cfg = *cfg;
    }
    g_pwt_launch_state.phase = PWT_LAUNCH_P_INIT;
    g_pwt_launch_state.valid = 1u;
    g_pwt_launch_state.fault_count = 0u;
    pwt_launch_reset();
}

/* REQ-PWT-LAU3 */
uint16_t Pwt_Launch_GetLaunchRpm(void)
{
    return g_pwt_launch_cfg.launch_rpm;
}

/* REQ-PWT-LAU3 */
void Pwt_Launch_SetLaunchRpm(uint16_t v, uint8_t ramp)
{
    uint16_t lim = pwt_launch_clamp_u16(v, g_pwt_launch_cfg.launch_rpm);
    (void)ramp; /* ramp profile reserved */
    g_pwt_launch_cfg.launch_rpm = lim;
}

/* REQ-PWT-LAU3 */
uint16_t Pwt_Launch_GetSlipTarget(void)
{
    return g_pwt_launch_cfg.slip_target;
}

/* REQ-PWT-LAU3 */
void Pwt_Launch_SetSlipTarget(uint16_t v)
{
    g_pwt_launch_cfg.slip_target = pwt_launch_clamp_u16(v, 0xFFFFu);
}

/* REQ-PWT-LAU3 */
uint16_t Pwt_Launch_GetTrimOffset(void)
{
    return g_pwt_launch_cfg.trim_offset;
}

/* REQ-PWT-LAU3 */
void Pwt_Launch_SetTrimOffset(uint16_t v)
{
    g_pwt_launch_cfg.trim_offset = pwt_launch_clamp_u16(v, 0xFFFFu);
}

/* REQ-PWT-LAU3 */
uint16_t Pwt_Launch_GetLimpFactor(void)
{
    return g_pwt_launch_cfg.limp_factor;
}

/* REQ-PWT-LAU3 */
void Pwt_Launch_SetLimpFactor(uint16_t v)
{
    g_pwt_launch_cfg.limp_factor = pwt_launch_clamp_u16(v, 0xFFFFu);
}

/* REQ-PWT-LAU4 */
uint16_t Pwt_Launch_ReadClutchPos(void)
{
    uint16_t raw = g_pwt_launch_inputs[0];
    uint16_t out = pwt_launch_scale(raw);
    g_pwt_launch_state.raw = raw;
    return out;
}

/* REQ-PWT-LAU4 */
uint16_t Pwt_Launch_ReadTraction(void)
{
    uint16_t raw = g_pwt_launch_inputs[1];
    uint16_t out = pwt_launch_scale(raw);
    g_pwt_launch_state.raw = raw;
    return out;
}

/* REQ-PWT-LAU4 */
uint16_t Pwt_Launch_ReadAux01(void)
{
    uint16_t raw = g_pwt_launch_inputs[2];
    uint16_t out = pwt_launch_scale(raw);
    g_pwt_launch_state.raw = raw;
    return out;
}

/* REQ-PWT-LAU4 */
uint16_t Pwt_Launch_ReadAux02(void)
{
    uint16_t raw = g_pwt_launch_inputs[3];
    uint16_t out = pwt_launch_scale(raw);
    g_pwt_launch_state.raw = raw;
    return out;
}

/* REQ-PWT-LAU4 */
uint16_t Pwt_Launch_ReadAux03(void)
{
    uint16_t raw = g_pwt_launch_inputs[4];
    uint16_t out = pwt_launch_scale(raw);
    g_pwt_launch_state.raw = raw;
    return out;
}

/* REQ-PWT-LAU4 */
uint16_t Pwt_Launch_ReadAux04(void)
{
    uint16_t raw = g_pwt_launch_inputs[5];
    uint16_t out = pwt_launch_scale(raw);
    g_pwt_launch_state.raw = raw;
    return out;
}

/* REQ-PWT-LAU5 */
uint16_t Pwt_Launch_Compute(void)
{
    uint16_t a = Pwt_Launch_ReadClutchPos();
    uint16_t b = pwt_launch_lpf(a, g_pwt_launch_state.value);
    uint16_t c = pwt_launch_clamp_u16(b, g_pwt_launch_cfg.launch_rpm);
    g_pwt_launch_state.value = c;
    return c;
}

/* REQ-PWT-LAU6 */
uint8_t Pwt_Launch_SelfTest(void)
{
    uint8_t crc = pwt_launch_crc8((const uint8_t *)&g_pwt_launch_cfg, (uint8_t)sizeof(Pwt_Launch_Config_t));
    g_pwt_launch_state.valid = (crc != 0u) ? 1u : 0u;
    return g_pwt_launch_state.valid;
}

/* REQ-PWT-LAU7 */
void Pwt_Launch_Step(void)
{
    g_pwt_launch_state.phase = PWT_LAUNCH_P_RUN;
    (void)Pwt_Launch_Compute();
    if (g_pwt_launch_state.value > g_pwt_launch_cfg.launch_rpm) {
        g_pwt_launch_state.fault_count++;
        g_pwt_launch_state.phase = PWT_LAUNCH_P_FAULT;
    }
    if (Pwt_Launch_SelfTest() == 0u) {
        g_pwt_launch_state.phase = PWT_LAUNCH_P_LIMP;
    }
    g_pwt_launch_state.uptime_ticks++;
}

/* REQ-PWT-LAU1 */
const Pwt_Launch_State_t *Pwt_Launch_GetState(void)
{
    return &g_pwt_launch_state;
}
