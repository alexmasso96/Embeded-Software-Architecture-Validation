#include "vcu_all.h"

/* ============================================================
 * BodyControl :: windows   (release R5.0)
 * Body Control Module: exterior/interior lighting, doors, wipers, windows and mirrors.
 * ============================================================ */

static Bcm_Windows_Config_t g_bcm_windows_cfg;
static Bcm_Windows_State_t g_bcm_windows_state;
static uint16_t g_bcm_windows_inputs[8];

static uint16_t bcm_windows_clamp_u16(uint16_t v, uint16_t hi);
static uint16_t bcm_windows_scale(uint16_t raw);
static uint16_t bcm_windows_lpf(uint16_t x, uint16_t prev);
static uint8_t bcm_windows_crc8(const uint8_t *p, uint8_t n);
static void bcm_windows_reset(void);

static uint16_t bcm_windows_clamp_u16(uint16_t v, uint16_t hi)
{
    return (v > hi) ? hi : v;
}

static uint16_t bcm_windows_scale(uint16_t raw)
{
    uint32_t s = ((uint32_t)raw * 1000u) >> 10;
    return (uint16_t)(s & 0xFFFFu);
}

static uint16_t bcm_windows_lpf(uint16_t x, uint16_t prev)
{
    /* first-order IIR low-pass: y = (3*prev + x) / 4 */
    return (uint16_t)(((uint32_t)prev * 3u + x) >> 2);
}

static uint8_t bcm_windows_crc8(const uint8_t *p, uint8_t n)
{
    uint8_t crc = 0xFFu;
    uint8_t i;
    for (i = 0u; i < n; i++) {
        crc = (uint8_t)(crc ^ p[i]);
        crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1Du : 0u));
    }
    return crc;
}

static void bcm_windows_reset(void)
{
    g_bcm_windows_state.value = 0u;
    g_bcm_windows_state.raw = 0u;
}

/* REQ-BCM-WIN2 */
void Bcm_Windows_Init(const Bcm_Windows_Config_t *cfg)
{
    if (cfg != 0) {
        g_bcm_windows_cfg = *cfg;
    }
    g_bcm_windows_state.phase = BCM_WINDOWS_P_INIT;
    g_bcm_windows_state.valid = 1u;
    g_bcm_windows_state.fault_count = 0u;
    bcm_windows_reset();
}

/* REQ-BCM-WIN3 */
uint16_t Bcm_Windows_GetMaxDuty(void)
{
    return g_bcm_windows_cfg.max_duty;
}

/* REQ-BCM-WIN3 */
void Bcm_Windows_SetMaxDuty(uint16_t v, uint8_t ramp)
{
    uint16_t lim = bcm_windows_clamp_u16(v, g_bcm_windows_cfg.max_duty);
    (void)ramp; /* ramp profile reserved */
    g_bcm_windows_cfg.max_duty = lim;
}

/* REQ-BCM-WIN3 */
uint16_t Bcm_Windows_GetPinchThreshMa(void)
{
    return g_bcm_windows_cfg.pinch_thresh_ma;
}

/* REQ-BCM-WIN3 */
void Bcm_Windows_SetPinchThreshMa(uint16_t v)
{
    g_bcm_windows_cfg.pinch_thresh_ma = bcm_windows_clamp_u16(v, 0xFFFFu);
}

/* REQ-BCM-WIN3 */
uint16_t Bcm_Windows_GetAutoStopMm(void)
{
    return g_bcm_windows_cfg.auto_stop_mm;
}

/* REQ-BCM-WIN3 */
void Bcm_Windows_SetAutoStopMm(uint16_t v)
{
    g_bcm_windows_cfg.auto_stop_mm = bcm_windows_clamp_u16(v, 0xFFFFu);
}

/* REQ-BCM-WIN3 */
uint16_t Bcm_Windows_GetTrimOffset(void)
{
    return g_bcm_windows_cfg.trim_offset;
}

/* REQ-BCM-WIN3 */
void Bcm_Windows_SetTrimOffset(uint16_t v)
{
    g_bcm_windows_cfg.trim_offset = bcm_windows_clamp_u16(v, 0xFFFFu);
}

/* REQ-BCM-WIN3 */
uint16_t Bcm_Windows_GetLimpFactor(void)
{
    return g_bcm_windows_cfg.limp_factor;
}

/* REQ-BCM-WIN3 */
void Bcm_Windows_SetLimpFactor(uint16_t v)
{
    g_bcm_windows_cfg.limp_factor = bcm_windows_clamp_u16(v, 0xFFFFu);
}

/* REQ-BCM-WIN4 */
uint16_t Bcm_Windows_ReadHallPos(void)
{
    uint16_t raw = g_bcm_windows_inputs[0];
    uint16_t out = bcm_windows_scale(raw);
    g_bcm_windows_state.raw = raw;
    return out;
}

/* REQ-BCM-WIN4 */
uint16_t Bcm_Windows_ReadCurrent(void)
{
    uint16_t raw = g_bcm_windows_inputs[1];
    uint16_t out = bcm_windows_scale(raw);
    g_bcm_windows_state.raw = raw;
    return out;
}

/* REQ-BCM-WIN4 */
uint16_t Bcm_Windows_ReadUpBtn(void)
{
    uint16_t raw = g_bcm_windows_inputs[2];
    uint16_t out = bcm_windows_scale(raw);
    g_bcm_windows_state.raw = raw;
    return out;
}

/* REQ-BCM-WIN4 */
uint16_t Bcm_Windows_ReadDownBtn(void)
{
    uint16_t raw = g_bcm_windows_inputs[3];
    uint16_t out = bcm_windows_scale(raw);
    g_bcm_windows_state.raw = raw;
    return out;
}

/* REQ-BCM-WIN4 */
uint16_t Bcm_Windows_ReadAux01(void)
{
    uint16_t raw = g_bcm_windows_inputs[4];
    uint16_t out = bcm_windows_scale(raw);
    g_bcm_windows_state.raw = raw;
    return out;
}

/* REQ-BCM-WIN4 */
uint16_t Bcm_Windows_ReadAux02(void)
{
    uint16_t raw = g_bcm_windows_inputs[5];
    uint16_t out = bcm_windows_scale(raw);
    g_bcm_windows_state.raw = raw;
    return out;
}

/* REQ-BCM-WIN4 */
uint16_t Bcm_Windows_ReadAux03(void)
{
    uint16_t raw = g_bcm_windows_inputs[6];
    uint16_t out = bcm_windows_scale(raw);
    g_bcm_windows_state.raw = raw;
    return out;
}

/* REQ-BCM-WIN4 */
uint16_t Bcm_Windows_ReadAux04(void)
{
    uint16_t raw = g_bcm_windows_inputs[7];
    uint16_t out = bcm_windows_scale(raw);
    g_bcm_windows_state.raw = raw;
    return out;
}

/* REQ-BCM-WIN5 */
uint16_t Bcm_Windows_Compute(void)
{
    uint16_t a = Bcm_Windows_ReadHallPos();
    uint16_t b = bcm_windows_lpf(a, g_bcm_windows_state.value);
    uint16_t c = bcm_windows_clamp_u16(b, g_bcm_windows_cfg.max_duty);
    g_bcm_windows_state.value = c;
    return c;
}

/* REQ-BCM-WIN6 */
uint8_t Bcm_Windows_SelfTest(void)
{
    uint8_t crc = bcm_windows_crc8((const uint8_t *)&g_bcm_windows_cfg, (uint8_t)sizeof(Bcm_Windows_Config_t));
    g_bcm_windows_state.valid = (crc != 0u) ? 1u : 0u;
    return g_bcm_windows_state.valid;
}

/* REQ-BCM-WIN7 */
void Bcm_Windows_Step(void)
{
    g_bcm_windows_state.phase = BCM_WINDOWS_P_RUN;
    (void)Bcm_Windows_Compute();
    if (g_bcm_windows_state.value > g_bcm_windows_cfg.max_duty) {
        g_bcm_windows_state.fault_count++;
        g_bcm_windows_state.phase = BCM_WINDOWS_P_FAULT;
    }
    if (Bcm_Windows_SelfTest() == 0u) {
        g_bcm_windows_state.phase = BCM_WINDOWS_P_LIMP;
    }
    g_bcm_windows_state.uptime_ticks++;
}

/* REQ-BCM-WIN1 */
const Bcm_Windows_State_t *Bcm_Windows_GetState(void)
{
    return &g_bcm_windows_state;
}
