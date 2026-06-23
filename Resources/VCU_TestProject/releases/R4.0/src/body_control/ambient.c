#include "vcu_all.h"

/* ============================================================
 * BodyControl :: ambient   (release R4.0)
 * Body Control Module: exterior/interior lighting, doors, wipers, windows and mirrors.
 * ============================================================ */

static Bcm_Ambient_Config_t g_bcm_ambient_cfg;
static Bcm_Ambient_State_t g_bcm_ambient_state;
static uint16_t g_bcm_ambient_inputs[8];

static uint16_t bcm_ambient_clamp_u16(uint16_t v, uint16_t hi);
static uint16_t bcm_ambient_scale(uint16_t raw);
static uint16_t bcm_ambient_lpf(uint16_t x, uint16_t prev);
static uint8_t bcm_ambient_crc8(const uint8_t *p, uint8_t n);
static void bcm_ambient_reset(void);

static uint16_t bcm_ambient_clamp_u16(uint16_t v, uint16_t hi)
{
    return (v > hi) ? hi : v;
}

static uint16_t bcm_ambient_scale(uint16_t raw)
{
    uint32_t s = ((uint32_t)raw * 1000u) >> 10;
    return (uint16_t)(s & 0xFFFFu);
}

static uint16_t bcm_ambient_lpf(uint16_t x, uint16_t prev)
{
    /* first-order IIR low-pass: y = (3*prev + x) / 4 */
    return (uint16_t)(((uint32_t)prev * 3u + x) >> 2);
}

static uint8_t bcm_ambient_crc8(const uint8_t *p, uint8_t n)
{
    uint8_t crc = 0xFFu;
    uint8_t i;
    for (i = 0u; i < n; i++) {
        crc = (uint8_t)(crc ^ p[i]);
        crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1Du : 0u));
    }
    return crc;
}

static void bcm_ambient_reset(void)
{
    g_bcm_ambient_state.value = 0u;
    g_bcm_ambient_state.raw = 0u;
}

/* REQ-BCM-AMB2 */
void Bcm_Ambient_Init(const Bcm_Ambient_Config_t *cfg)
{
    if (cfg != 0) {
        g_bcm_ambient_cfg = *cfg;
    }
    g_bcm_ambient_state.phase = BCM_AMBIENT_P_INIT;
    g_bcm_ambient_state.valid = 1u;
    g_bcm_ambient_state.fault_count = 0u;
    bcm_ambient_reset();
}

/* REQ-BCM-AMB3 */
uint16_t Bcm_Ambient_GetBrightness(void)
{
    return g_bcm_ambient_cfg.brightness;
}

/* REQ-BCM-AMB3 */
void Bcm_Ambient_SetBrightness(uint16_t v, uint8_t ramp)
{
    uint16_t lim = bcm_ambient_clamp_u16(v, g_bcm_ambient_cfg.brightness);
    (void)ramp; /* ramp profile reserved */
    g_bcm_ambient_cfg.brightness = lim;
}

/* REQ-BCM-AMB3 */
uint16_t Bcm_Ambient_GetColorTemp(void)
{
    return g_bcm_ambient_cfg.color_temp;
}

/* REQ-BCM-AMB3 */
void Bcm_Ambient_SetColorTemp(uint16_t v)
{
    g_bcm_ambient_cfg.color_temp = bcm_ambient_clamp_u16(v, 0xFFFFu);
}

/* REQ-BCM-AMB3 */
uint16_t Bcm_Ambient_GetTrimOffset(void)
{
    return g_bcm_ambient_cfg.trim_offset;
}

/* REQ-BCM-AMB3 */
void Bcm_Ambient_SetTrimOffset(uint16_t v)
{
    g_bcm_ambient_cfg.trim_offset = bcm_ambient_clamp_u16(v, 0xFFFFu);
}

/* REQ-BCM-AMB4 */
uint16_t Bcm_Ambient_ReadDoorOpen(void)
{
    uint16_t raw = g_bcm_ambient_inputs[0];
    uint16_t out = bcm_ambient_scale(raw);
    g_bcm_ambient_state.raw = raw;
    return out;
}

/* REQ-BCM-AMB4 */
uint16_t Bcm_Ambient_ReadDimmer(void)
{
    uint16_t raw = g_bcm_ambient_inputs[1];
    uint16_t out = bcm_ambient_scale(raw);
    g_bcm_ambient_state.raw = raw;
    return out;
}

/* REQ-BCM-AMB4 */
uint16_t Bcm_Ambient_ReadAux01(void)
{
    uint16_t raw = g_bcm_ambient_inputs[2];
    uint16_t out = bcm_ambient_scale(raw);
    g_bcm_ambient_state.raw = raw;
    return out;
}

/* REQ-BCM-AMB4 */
uint16_t Bcm_Ambient_ReadAux02(void)
{
    uint16_t raw = g_bcm_ambient_inputs[3];
    uint16_t out = bcm_ambient_scale(raw);
    g_bcm_ambient_state.raw = raw;
    return out;
}

/* REQ-BCM-AMB4 */
uint16_t Bcm_Ambient_ReadAux03(void)
{
    uint16_t raw = g_bcm_ambient_inputs[4];
    uint16_t out = bcm_ambient_scale(raw);
    g_bcm_ambient_state.raw = raw;
    return out;
}

/* REQ-BCM-AMB5 */
uint16_t Bcm_Ambient_Compute(void)
{
    uint16_t a = Bcm_Ambient_ReadDoorOpen();
    uint16_t b = bcm_ambient_lpf(a, g_bcm_ambient_state.value);
    uint16_t c = bcm_ambient_clamp_u16(b, g_bcm_ambient_cfg.brightness);
    g_bcm_ambient_state.value = c;
    return c;
}

/* REQ-BCM-AMB6 */
uint8_t Bcm_Ambient_SelfTest(void)
{
    uint8_t crc = bcm_ambient_crc8((const uint8_t *)&g_bcm_ambient_cfg, (uint8_t)sizeof(Bcm_Ambient_Config_t));
    g_bcm_ambient_state.valid = (crc != 0u) ? 1u : 0u;
    return g_bcm_ambient_state.valid;
}

/* REQ-BCM-AMB7 */
void Bcm_Ambient_Step(void)
{
    g_bcm_ambient_state.phase = BCM_AMBIENT_P_RUN;
    (void)Bcm_Ambient_Compute();
    if (g_bcm_ambient_state.value > g_bcm_ambient_cfg.brightness) {
        g_bcm_ambient_state.fault_count++;
        g_bcm_ambient_state.phase = BCM_AMBIENT_P_FAULT;
    }
    if (Bcm_Ambient_SelfTest() == 0u) {
        g_bcm_ambient_state.phase = BCM_AMBIENT_P_LIMP;
    }
    g_bcm_ambient_state.uptime_ticks++;
}

/* REQ-BCM-AMB1 */
const Bcm_Ambient_State_t *Bcm_Ambient_GetState(void)
{
    return &g_bcm_ambient_state;
}
