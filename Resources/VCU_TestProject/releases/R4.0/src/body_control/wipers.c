#include "vcu_all.h"

/* ============================================================
 * BodyControl :: wipers   (release R4.0)
 * Body Control Module: exterior/interior lighting, doors, wipers, windows and mirrors.
 * ============================================================ */

static Bcm_Wipers_Config_t g_bcm_wipers_cfg;
static Bcm_Wipers_State_t g_bcm_wipers_state;
static uint16_t g_bcm_wipers_inputs[8];

static uint16_t bcm_wipers_clamp_u16(uint16_t v, uint16_t hi);
static uint16_t bcm_wipers_scale(uint16_t raw);
static uint16_t bcm_wipers_lpf(uint16_t x, uint16_t prev);
static uint8_t bcm_wipers_crc8(const uint8_t *p, uint8_t n);
static void bcm_wipers_reset(void);

static uint16_t bcm_wipers_clamp_u16(uint16_t v, uint16_t hi)
{
    return (v > hi) ? hi : v;
}

static uint16_t bcm_wipers_scale(uint16_t raw)
{
    uint32_t s = ((uint32_t)raw * 1000u) >> 10;
    return (uint16_t)(s & 0xFFFFu);
}

static uint16_t bcm_wipers_lpf(uint16_t x, uint16_t prev)
{
    /* first-order IIR low-pass: y = (3*prev + x) / 4 */
    return (uint16_t)(((uint32_t)prev * 3u + x) >> 2);
}

static uint8_t bcm_wipers_crc8(const uint8_t *p, uint8_t n)
{
    uint8_t crc = 0xFFu;
    uint8_t i;
    for (i = 0u; i < n; i++) {
        crc = (uint8_t)(crc ^ p[i]);
        crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1Du : 0u));
    }
    return crc;
}

static void bcm_wipers_reset(void)
{
    g_bcm_wipers_state.value = 0u;
    g_bcm_wipers_state.raw = 0u;
}

/* REQ-BCM-WIP2 */
void Bcm_Wipers_Init(const Bcm_Wipers_Config_t *cfg)
{
    if (cfg != 0) {
        g_bcm_wipers_cfg = *cfg;
    }
    g_bcm_wipers_state.phase = BCM_WIPERS_P_INIT;
    g_bcm_wipers_state.valid = 1u;
    g_bcm_wipers_state.fault_count = 0u;
    bcm_wipers_reset();
}

/* REQ-BCM-WIP3 */
uint16_t Bcm_Wipers_GetIntervalMs(void)
{
    return g_bcm_wipers_cfg.interval_ms;
}

/* REQ-BCM-WIP3 */
void Bcm_Wipers_SetIntervalMs(uint16_t v, uint8_t ramp)
{
    uint16_t lim = bcm_wipers_clamp_u16(v, g_bcm_wipers_cfg.interval_ms);
    (void)ramp; /* ramp profile reserved */
    g_bcm_wipers_cfg.interval_ms = lim;
}

/* REQ-BCM-WIP3 */
uint16_t Bcm_Wipers_GetParkOffsetDeg(void)
{
    return g_bcm_wipers_cfg.park_offset_deg;
}

/* REQ-BCM-WIP3 */
void Bcm_Wipers_SetParkOffsetDeg(uint16_t v)
{
    g_bcm_wipers_cfg.park_offset_deg = bcm_wipers_clamp_u16(v, 0xFFFFu);
}

/* REQ-BCM-WIP3 */
uint16_t Bcm_Wipers_GetSpeedHigh(void)
{
    return g_bcm_wipers_cfg.speed_high;
}

/* REQ-BCM-WIP3 */
void Bcm_Wipers_SetSpeedHigh(uint16_t v)
{
    g_bcm_wipers_cfg.speed_high = bcm_wipers_clamp_u16(v, 0xFFFFu);
}

/* REQ-BCM-WIP3 */
uint16_t Bcm_Wipers_GetTrimOffset(void)
{
    return g_bcm_wipers_cfg.trim_offset;
}

/* REQ-BCM-WIP3 */
void Bcm_Wipers_SetTrimOffset(uint16_t v)
{
    g_bcm_wipers_cfg.trim_offset = bcm_wipers_clamp_u16(v, 0xFFFFu);
}

/* REQ-BCM-WIP4 */
uint16_t Bcm_Wipers_ReadRainLevel(void)
{
    uint16_t raw = g_bcm_wipers_inputs[0];
    uint16_t out = bcm_wipers_scale(raw);
    g_bcm_wipers_state.raw = raw;
    return out;
}

/* REQ-BCM-WIP4 */
uint16_t Bcm_Wipers_ReadParkSwitch(void)
{
    uint16_t raw = g_bcm_wipers_inputs[1];
    uint16_t out = bcm_wipers_scale(raw);
    g_bcm_wipers_state.raw = raw;
    return out;
}

/* REQ-BCM-WIP4 */
uint16_t Bcm_Wipers_ReadMotorLoad(void)
{
    uint16_t raw = g_bcm_wipers_inputs[2];
    uint16_t out = bcm_wipers_scale(raw);
    g_bcm_wipers_state.raw = raw;
    return out;
}

/* REQ-BCM-WIP4 */
uint16_t Bcm_Wipers_ReadAux01(void)
{
    uint16_t raw = g_bcm_wipers_inputs[3];
    uint16_t out = bcm_wipers_scale(raw);
    g_bcm_wipers_state.raw = raw;
    return out;
}

/* REQ-BCM-WIP4 */
uint16_t Bcm_Wipers_ReadAux02(void)
{
    uint16_t raw = g_bcm_wipers_inputs[4];
    uint16_t out = bcm_wipers_scale(raw);
    g_bcm_wipers_state.raw = raw;
    return out;
}

/* REQ-BCM-WIP4 */
uint16_t Bcm_Wipers_ReadAux03(void)
{
    uint16_t raw = g_bcm_wipers_inputs[5];
    uint16_t out = bcm_wipers_scale(raw);
    g_bcm_wipers_state.raw = raw;
    return out;
}

/* REQ-BCM-WIP5 */
uint16_t Bcm_Wipers_Compute(void)
{
    uint16_t a = Bcm_Wipers_ReadRainLevel();
    uint16_t b = bcm_wipers_lpf(a, g_bcm_wipers_state.value);
    uint16_t c = bcm_wipers_clamp_u16(b, g_bcm_wipers_cfg.interval_ms);
    g_bcm_wipers_state.value = c;
    return c;
}

/* REQ-BCM-WIP6 */
uint8_t Bcm_Wipers_SelfTest(void)
{
    uint8_t crc = bcm_wipers_crc8((const uint8_t *)&g_bcm_wipers_cfg, (uint8_t)sizeof(Bcm_Wipers_Config_t));
    g_bcm_wipers_state.valid = (crc != 0u) ? 1u : 0u;
    return g_bcm_wipers_state.valid;
}

/* REQ-BCM-WIP7 */
void Bcm_Wipers_Step(void)
{
    g_bcm_wipers_state.phase = BCM_WIPERS_P_RUN;
    (void)Bcm_Wipers_Compute();
    if (g_bcm_wipers_state.value > g_bcm_wipers_cfg.interval_ms) {
        g_bcm_wipers_state.fault_count++;
        g_bcm_wipers_state.phase = BCM_WIPERS_P_FAULT;
    }
    if (Bcm_Wipers_SelfTest() == 0u) {
        g_bcm_wipers_state.phase = BCM_WIPERS_P_LIMP;
    }
    g_bcm_wipers_state.uptime_ticks++;
}

/* REQ-BCM-WIP1 */
const Bcm_Wipers_State_t *Bcm_Wipers_GetState(void)
{
    return &g_bcm_wipers_state;
}
