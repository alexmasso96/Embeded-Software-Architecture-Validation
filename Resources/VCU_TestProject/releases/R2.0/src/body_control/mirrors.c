#include "vcu_all.h"

/* ============================================================
 * BodyControl :: mirrors   (release R2.0)
 * Body Control Module: exterior/interior lighting, doors, wipers, windows and mirrors.
 * ============================================================ */

static Bcm_Mirrors_Config_t g_bcm_mirrors_cfg;
static Bcm_Mirrors_State_t g_bcm_mirrors_state;
static uint16_t g_bcm_mirrors_inputs[8];

static uint16_t bcm_mirrors_clamp_u16(uint16_t v, uint16_t hi);
static uint16_t bcm_mirrors_scale(uint16_t raw);
static uint16_t bcm_mirrors_lpf(uint16_t x, uint16_t prev);
static uint8_t bcm_mirrors_crc8(const uint8_t *p, uint8_t n);
static void bcm_mirrors_reset(void);

static uint16_t bcm_mirrors_clamp_u16(uint16_t v, uint16_t hi)
{
    return (v > hi) ? hi : v;
}

static uint16_t bcm_mirrors_scale(uint16_t raw)
{
    uint32_t s = ((uint32_t)raw * 1000u) >> 10;
    return (uint16_t)(s & 0xFFFFu);
}

static uint16_t bcm_mirrors_lpf(uint16_t x, uint16_t prev)
{
    /* first-order IIR low-pass: y = (3*prev + x) / 4 */
    return (uint16_t)(((uint32_t)prev * 3u + x) >> 2);
}

static uint8_t bcm_mirrors_crc8(const uint8_t *p, uint8_t n)
{
    uint8_t crc = 0xFFu;
    uint8_t i;
    for (i = 0u; i < n; i++) {
        crc = (uint8_t)(crc ^ p[i]);
        crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1Du : 0u));
    }
    return crc;
}

static void bcm_mirrors_reset(void)
{
    g_bcm_mirrors_state.value = 0u;
    g_bcm_mirrors_state.raw = 0u;
}

/* REQ-BCM-MIR2 */
void Bcm_Mirrors_Init(const Bcm_Mirrors_Config_t *cfg)
{
    if (cfg != 0) {
        g_bcm_mirrors_cfg = *cfg;
    }
    g_bcm_mirrors_state.phase = BCM_MIRRORS_P_INIT;
    g_bcm_mirrors_state.valid = 1u;
    g_bcm_mirrors_state.fault_count = 0u;
    bcm_mirrors_reset();
}

/* REQ-BCM-MIR3 */
uint16_t Bcm_Mirrors_GetFoldAngle(void)
{
    return g_bcm_mirrors_cfg.fold_angle;
}

/* REQ-BCM-MIR3 */
void Bcm_Mirrors_SetFoldAngle(uint16_t v)
{
    g_bcm_mirrors_cfg.fold_angle = bcm_mirrors_clamp_u16(v, 0xFFFFu);
}

/* REQ-BCM-MIR3 */
uint16_t Bcm_Mirrors_GetHeatPwm(void)
{
    return g_bcm_mirrors_cfg.heat_pwm;
}

/* REQ-BCM-MIR3 */
void Bcm_Mirrors_SetHeatPwm(uint16_t v)
{
    g_bcm_mirrors_cfg.heat_pwm = bcm_mirrors_clamp_u16(v, 0xFFFFu);
}

/* REQ-BCM-MIR4 */
uint16_t Bcm_Mirrors_ReadFoldSwitch(void)
{
    uint16_t raw = g_bcm_mirrors_inputs[0];
    uint16_t out = bcm_mirrors_scale(raw);
    g_bcm_mirrors_state.raw = raw;
    return out;
}

/* REQ-BCM-MIR4 */
uint16_t Bcm_Mirrors_ReadTiltPot(void)
{
    uint16_t raw = g_bcm_mirrors_inputs[1];
    uint16_t out = bcm_mirrors_scale(raw);
    g_bcm_mirrors_state.raw = raw;
    return out;
}

/* REQ-BCM-MIR4 */
uint16_t Bcm_Mirrors_ReadAux01(void)
{
    uint16_t raw = g_bcm_mirrors_inputs[2];
    uint16_t out = bcm_mirrors_scale(raw);
    g_bcm_mirrors_state.raw = raw;
    return out;
}

/* REQ-BCM-MIR5 */
uint16_t Bcm_Mirrors_Compute(void)
{
    uint16_t a = Bcm_Mirrors_ReadFoldSwitch();
    uint16_t b = bcm_mirrors_lpf(a, g_bcm_mirrors_state.value);
    uint16_t c = bcm_mirrors_clamp_u16(b, g_bcm_mirrors_cfg.fold_angle);
    g_bcm_mirrors_state.value = c;
    return c;
}

/* REQ-BCM-MIR7 */
void Bcm_Mirrors_Step(void)
{
    g_bcm_mirrors_state.phase = BCM_MIRRORS_P_RUN;
    (void)Bcm_Mirrors_Compute();
    if (g_bcm_mirrors_state.value > g_bcm_mirrors_cfg.fold_angle) {
        g_bcm_mirrors_state.fault_count++;
        g_bcm_mirrors_state.phase = BCM_MIRRORS_P_FAULT;
    }
}

/* REQ-BCM-MIR1 */
const Bcm_Mirrors_State_t *Bcm_Mirrors_GetState(void)
{
    return &g_bcm_mirrors_state;
}
