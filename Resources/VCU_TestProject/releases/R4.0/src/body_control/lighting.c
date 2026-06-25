#include "vcu_all.h"

/* ============================================================
 * BodyControl :: lighting   (release R4.0)
 * Body Control Module: exterior/interior lighting, doors, wipers, windows and mirrors.
 * ============================================================ */

static Bcm_Lighting_Config_t g_bcm_lighting_cfg;
static Bcm_Lighting_State_t g_bcm_lighting_state;
static uint16_t g_bcm_lighting_inputs[8];

static uint16_t bcm_lighting_clamp_u16(uint16_t v, uint16_t hi);
static uint16_t bcm_lighting_scale(uint16_t raw);
static uint16_t bcm_lighting_lpf(uint16_t x, uint16_t prev);
static uint8_t bcm_lighting_crc8(const uint8_t *p, uint8_t n);
static void bcm_lighting_reset(void);

static uint16_t bcm_lighting_clamp_u16(uint16_t v, uint16_t hi)
{
    return (v > hi) ? hi : v;
}

static uint16_t bcm_lighting_scale(uint16_t raw)
{
    uint32_t s = ((uint32_t)raw * 1000u) >> 10;
    return (uint16_t)(s & 0xFFFFu);
}

static uint16_t bcm_lighting_lpf(uint16_t x, uint16_t prev)
{
    /* first-order IIR low-pass: y = (3*prev + x) / 4 */
    return (uint16_t)(((uint32_t)prev * 3u + x) >> 2);
}

static uint8_t bcm_lighting_crc8(const uint8_t *p, uint8_t n)
{
    uint8_t crc = 0xFFu;
    uint8_t i;
    for (i = 0u; i < n; i++) {
        crc = (uint8_t)(crc ^ p[i]);
        crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1Du : 0u));
    }
    return crc;
}

static void bcm_lighting_reset(void)
{
    g_bcm_lighting_state.value = 0u;
    g_bcm_lighting_state.raw = 0u;
}

/* REQ-BCM-LIG2 */
void Bcm_Lighting_Init(const Bcm_Lighting_Config_t *cfg)
{
    if (cfg != 0) {
        g_bcm_lighting_cfg = *cfg;
    }
    g_bcm_lighting_state.phase = BCM_LIGHTING_P_INIT;
    g_bcm_lighting_state.valid = 1u;
    g_bcm_lighting_state.fault_count = 0u;
    bcm_lighting_reset();
}

/* REQ-BCM-LIG3 */
uint16_t Bcm_Lighting_GetMaxCurrentMa(void)
{
    return g_bcm_lighting_cfg.max_current_ma;
}

/* REQ-BCM-LIG3 */
void Bcm_Lighting_SetMaxCurrentMa(uint16_t v, uint8_t ramp)
{
    uint16_t lim = bcm_lighting_clamp_u16(v, g_bcm_lighting_cfg.max_current_ma);
    (void)ramp; /* ramp profile reserved */
    g_bcm_lighting_cfg.max_current_ma = lim;
}

/* REQ-BCM-LIG3 */
uint16_t Bcm_Lighting_GetDimRatePctS(void)
{
    return g_bcm_lighting_cfg.dim_rate_pct_s;
}

/* REQ-BCM-LIG3 */
void Bcm_Lighting_SetDimRatePctS(uint16_t v)
{
    g_bcm_lighting_cfg.dim_rate_pct_s = bcm_lighting_clamp_u16(v, 0xFFFFu);
}

/* REQ-BCM-LIG3 */
uint16_t Bcm_Lighting_GetFadeMs(void)
{
    return g_bcm_lighting_cfg.fade_ms;
}

/* REQ-BCM-LIG3 */
void Bcm_Lighting_SetFadeMs(uint16_t v)
{
    g_bcm_lighting_cfg.fade_ms = bcm_lighting_clamp_u16(v, 0xFFFFu);
}

/* REQ-BCM-LIG3 */
uint16_t Bcm_Lighting_GetTrimOffset(void)
{
    return g_bcm_lighting_cfg.trim_offset;
}

/* REQ-BCM-LIG3 */
void Bcm_Lighting_SetTrimOffset(uint16_t v)
{
    g_bcm_lighting_cfg.trim_offset = bcm_lighting_clamp_u16(v, 0xFFFFu);
}

/* REQ-BCM-LIG4 */
uint16_t Bcm_Lighting_ReadSwitch(void)
{
    uint16_t raw = g_bcm_lighting_inputs[0];
    uint16_t out = bcm_lighting_scale(raw);
    g_bcm_lighting_state.raw = raw;
    return out;
}

/* REQ-BCM-LIG4 */
uint16_t Bcm_Lighting_ReadBusVoltage(void)
{
    uint16_t raw = g_bcm_lighting_inputs[1];
    uint16_t out = bcm_lighting_scale(raw);
    g_bcm_lighting_state.raw = raw;
    return out;
}

/* REQ-BCM-LIG4 */
uint16_t Bcm_Lighting_ReadAmbientLux(void)
{
    uint16_t raw = g_bcm_lighting_inputs[2];
    uint16_t out = bcm_lighting_scale(raw);
    g_bcm_lighting_state.raw = raw;
    return out;
}

/* REQ-BCM-LIG4 */
uint16_t Bcm_Lighting_ReadAux01(void)
{
    uint16_t raw = g_bcm_lighting_inputs[3];
    uint16_t out = bcm_lighting_scale(raw);
    g_bcm_lighting_state.raw = raw;
    return out;
}

/* REQ-BCM-LIG4 */
uint16_t Bcm_Lighting_ReadAux02(void)
{
    uint16_t raw = g_bcm_lighting_inputs[4];
    uint16_t out = bcm_lighting_scale(raw);
    g_bcm_lighting_state.raw = raw;
    return out;
}

/* REQ-BCM-LIG4 */
uint16_t Bcm_Lighting_ReadAux03(void)
{
    uint16_t raw = g_bcm_lighting_inputs[5];
    uint16_t out = bcm_lighting_scale(raw);
    g_bcm_lighting_state.raw = raw;
    return out;
}

/* REQ-BCM-LIG5 */
uint16_t Bcm_Lighting_Compute(void)
{
    uint16_t a = Bcm_Lighting_ReadSwitch();
    uint16_t b = bcm_lighting_lpf(a, g_bcm_lighting_state.value);
    uint16_t c = bcm_lighting_clamp_u16(b, g_bcm_lighting_cfg.max_current_ma);
    g_bcm_lighting_state.value = c;
    return c;
}

/* REQ-BCM-LIG6 */
uint8_t Bcm_Lighting_SelfTest(void)
{
    uint8_t crc = bcm_lighting_crc8((const uint8_t *)&g_bcm_lighting_cfg, (uint8_t)sizeof(Bcm_Lighting_Config_t));
    g_bcm_lighting_state.valid = (crc != 0u) ? 1u : 0u;
    return g_bcm_lighting_state.valid;
}

/* REQ-BCM-LIG7 */
void Bcm_Lighting_Step(void)
{
    g_bcm_lighting_state.phase = BCM_LIGHTING_P_RUN;
    (void)Bcm_Lighting_Compute();
    if (g_bcm_lighting_state.value > g_bcm_lighting_cfg.max_current_ma) {
        g_bcm_lighting_state.fault_count++;
        g_bcm_lighting_state.phase = BCM_LIGHTING_P_FAULT;
    }
    if (Bcm_Lighting_SelfTest() == 0u) {
        g_bcm_lighting_state.phase = BCM_LIGHTING_P_LIMP;
    }
    g_bcm_lighting_state.uptime_ticks++;
}

/* REQ-BCM-LIG1 */
const Bcm_Lighting_State_t *Bcm_Lighting_GetState(void)
{
    return &g_bcm_lighting_state;
}
