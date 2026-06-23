#include "vcu_all.h"

/* ============================================================
 * ChassisControl :: suspension   (release R5.0)
 * Chassis Control (introduced R2.0): ABS, traction, steering assist and suspension.
 * ============================================================ */

static Chs_Suspension_Config_t g_chs_suspension_cfg;
static Chs_Suspension_State_t g_chs_suspension_state;
static uint16_t g_chs_suspension_inputs[8];

static uint16_t chs_suspension_clamp_u16(uint16_t v, uint16_t hi);
static uint16_t chs_suspension_scale(uint16_t raw);
static uint16_t chs_suspension_lpf(uint16_t x, uint16_t prev);
static uint8_t chs_suspension_crc8(const uint8_t *p, uint8_t n);
static void chs_suspension_reset(void);

static uint16_t chs_suspension_clamp_u16(uint16_t v, uint16_t hi)
{
    return (v > hi) ? hi : v;
}

static uint16_t chs_suspension_scale(uint16_t raw)
{
    uint32_t s = ((uint32_t)raw * 1000u) >> 10;
    return (uint16_t)(s & 0xFFFFu);
}

static uint16_t chs_suspension_lpf(uint16_t x, uint16_t prev)
{
    /* first-order IIR low-pass: y = (3*prev + x) / 4 */
    return (uint16_t)(((uint32_t)prev * 3u + x) >> 2);
}

static uint8_t chs_suspension_crc8(const uint8_t *p, uint8_t n)
{
    uint8_t crc = 0xFFu;
    uint8_t i;
    for (i = 0u; i < n; i++) {
        crc = (uint8_t)(crc ^ p[i]);
        crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1Du : 0u));
    }
    return crc;
}

static void chs_suspension_reset(void)
{
    g_chs_suspension_state.value = 0u;
    g_chs_suspension_state.raw = 0u;
}

/* REQ-CHS-SUS2 */
void Chs_Suspension_Init(const Chs_Suspension_Config_t *cfg)
{
    if (cfg != 0) {
        g_chs_suspension_cfg = *cfg;
    }
    g_chs_suspension_state.phase = CHS_SUSPENSION_P_INIT;
    g_chs_suspension_state.valid = 1u;
    g_chs_suspension_state.fault_count = 0u;
    chs_suspension_reset();
}

/* REQ-CHS-SUS3 */
uint16_t Chs_Suspension_GetDampSoft(void)
{
    return g_chs_suspension_cfg.damp_soft;
}

/* REQ-CHS-SUS3 */
void Chs_Suspension_SetDampSoft(uint16_t v, uint8_t ramp)
{
    uint16_t lim = chs_suspension_clamp_u16(v, g_chs_suspension_cfg.damp_soft);
    (void)ramp; /* ramp profile reserved */
    g_chs_suspension_cfg.damp_soft = lim;
}

/* REQ-CHS-SUS3 */
uint16_t Chs_Suspension_GetDampHard(void)
{
    return g_chs_suspension_cfg.damp_hard;
}

/* REQ-CHS-SUS3 */
void Chs_Suspension_SetDampHard(uint16_t v)
{
    g_chs_suspension_cfg.damp_hard = chs_suspension_clamp_u16(v, 0xFFFFu);
}

/* REQ-CHS-SUS3 */
uint16_t Chs_Suspension_GetTrimOffset(void)
{
    return g_chs_suspension_cfg.trim_offset;
}

/* REQ-CHS-SUS3 */
void Chs_Suspension_SetTrimOffset(uint16_t v)
{
    g_chs_suspension_cfg.trim_offset = chs_suspension_clamp_u16(v, 0xFFFFu);
}

/* REQ-CHS-SUS3 */
uint16_t Chs_Suspension_GetLimpFactor(void)
{
    return g_chs_suspension_cfg.limp_factor;
}

/* REQ-CHS-SUS3 */
void Chs_Suspension_SetLimpFactor(uint16_t v)
{
    g_chs_suspension_cfg.limp_factor = chs_suspension_clamp_u16(v, 0xFFFFu);
}

/* REQ-CHS-SUS4 */
uint16_t Chs_Suspension_ReadHeightFL(void)
{
    uint16_t raw = g_chs_suspension_inputs[0];
    uint16_t out = chs_suspension_scale(raw);
    g_chs_suspension_state.raw = raw;
    return out;
}

/* REQ-CHS-SUS4 */
uint16_t Chs_Suspension_ReadHeightFR(void)
{
    uint16_t raw = g_chs_suspension_inputs[1];
    uint16_t out = chs_suspension_scale(raw);
    g_chs_suspension_state.raw = raw;
    return out;
}

/* REQ-CHS-SUS4 */
uint16_t Chs_Suspension_ReadAccelZ(void)
{
    uint16_t raw = g_chs_suspension_inputs[2];
    uint16_t out = chs_suspension_scale(raw);
    g_chs_suspension_state.raw = raw;
    return out;
}

/* REQ-CHS-SUS4 */
uint16_t Chs_Suspension_ReadAux01(void)
{
    uint16_t raw = g_chs_suspension_inputs[3];
    uint16_t out = chs_suspension_scale(raw);
    g_chs_suspension_state.raw = raw;
    return out;
}

/* REQ-CHS-SUS4 */
uint16_t Chs_Suspension_ReadAux02(void)
{
    uint16_t raw = g_chs_suspension_inputs[4];
    uint16_t out = chs_suspension_scale(raw);
    g_chs_suspension_state.raw = raw;
    return out;
}

/* REQ-CHS-SUS4 */
uint16_t Chs_Suspension_ReadAux03(void)
{
    uint16_t raw = g_chs_suspension_inputs[5];
    uint16_t out = chs_suspension_scale(raw);
    g_chs_suspension_state.raw = raw;
    return out;
}

/* REQ-CHS-SUS4 */
uint16_t Chs_Suspension_ReadAux04(void)
{
    uint16_t raw = g_chs_suspension_inputs[6];
    uint16_t out = chs_suspension_scale(raw);
    g_chs_suspension_state.raw = raw;
    return out;
}

/* REQ-CHS-SUS5 */
uint16_t Chs_Suspension_Compute(void)
{
    uint16_t a = Chs_Suspension_ReadHeightFL();
    uint16_t b = chs_suspension_lpf(a, g_chs_suspension_state.value);
    uint16_t c = chs_suspension_clamp_u16(b, g_chs_suspension_cfg.damp_soft);
    g_chs_suspension_state.value = c;
    return c;
}

/* REQ-CHS-SUS6 */
uint8_t Chs_Suspension_SelfTest(void)
{
    uint8_t crc = chs_suspension_crc8((const uint8_t *)&g_chs_suspension_cfg, (uint8_t)sizeof(Chs_Suspension_Config_t));
    g_chs_suspension_state.valid = (crc != 0u) ? 1u : 0u;
    return g_chs_suspension_state.valid;
}

/* REQ-CHS-SUS7 */
void Chs_Suspension_Step(void)
{
    g_chs_suspension_state.phase = CHS_SUSPENSION_P_RUN;
    (void)Chs_Suspension_Compute();
    if (g_chs_suspension_state.value > g_chs_suspension_cfg.damp_soft) {
        g_chs_suspension_state.fault_count++;
        g_chs_suspension_state.phase = CHS_SUSPENSION_P_FAULT;
    }
    if (Chs_Suspension_SelfTest() == 0u) {
        g_chs_suspension_state.phase = CHS_SUSPENSION_P_LIMP;
    }
    g_chs_suspension_state.uptime_ticks++;
}

/* REQ-CHS-SUS1 */
const Chs_Suspension_State_t *Chs_Suspension_GetState(void)
{
    return &g_chs_suspension_state;
}
