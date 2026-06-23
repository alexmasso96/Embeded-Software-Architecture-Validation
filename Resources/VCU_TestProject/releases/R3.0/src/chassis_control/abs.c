#include "vcu_all.h"

/* ============================================================
 * ChassisControl :: abs   (release R3.0)
 * Chassis Control (introduced R2.0): ABS, traction, steering assist and suspension.
 * ============================================================ */

static Chs_Abs_Config_t g_chs_abs_cfg;
static Chs_Abs_State_t g_chs_abs_state;
static uint16_t g_chs_abs_inputs[8];

static uint16_t chs_abs_clamp_u16(uint16_t v, uint16_t hi);
static uint16_t chs_abs_scale(uint16_t raw);
static uint16_t chs_abs_lpf(uint16_t x, uint16_t prev);
static uint8_t chs_abs_crc8(const uint8_t *p, uint8_t n);
static void chs_abs_reset(void);

static uint16_t chs_abs_clamp_u16(uint16_t v, uint16_t hi)
{
    return (v > hi) ? hi : v;
}

static uint16_t chs_abs_scale(uint16_t raw)
{
    uint32_t s = ((uint32_t)raw * 1000u) >> 10;
    return (uint16_t)(s & 0xFFFFu);
}

static uint16_t chs_abs_lpf(uint16_t x, uint16_t prev)
{
    /* first-order IIR low-pass: y = (3*prev + x) / 4 */
    return (uint16_t)(((uint32_t)prev * 3u + x) >> 2);
}

static uint8_t chs_abs_crc8(const uint8_t *p, uint8_t n)
{
    uint8_t crc = 0xFFu;
    uint8_t i;
    for (i = 0u; i < n; i++) {
        crc = (uint8_t)(crc ^ p[i]);
        crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1Du : 0u));
    }
    return crc;
}

static void chs_abs_reset(void)
{
    g_chs_abs_state.value = 0u;
    g_chs_abs_state.raw = 0u;
}

/* REQ-CHS-ABS2 */
void Chs_Abs_Init(const Chs_Abs_Config_t *cfg)
{
    if (cfg != 0) {
        g_chs_abs_cfg = *cfg;
    }
    g_chs_abs_state.phase = CHS_ABS_P_INIT;
    g_chs_abs_state.valid = 1u;
    g_chs_abs_state.fault_count = 0u;
    chs_abs_reset();
}

/* REQ-CHS-ABS3 */
uint16_t Chs_Abs_GetSlipThreshPct(void)
{
    return g_chs_abs_cfg.slip_thresh_pct;
}

/* REQ-CHS-ABS3 */
void Chs_Abs_SetSlipThreshPct(uint16_t v)
{
    g_chs_abs_cfg.slip_thresh_pct = chs_abs_clamp_u16(v, 0xFFFFu);
}

/* REQ-CHS-ABS3 */
uint16_t Chs_Abs_GetPulseMs(void)
{
    return g_chs_abs_cfg.pulse_ms;
}

/* REQ-CHS-ABS3 */
void Chs_Abs_SetPulseMs(uint16_t v)
{
    g_chs_abs_cfg.pulse_ms = chs_abs_clamp_u16(v, 0xFFFFu);
}

/* REQ-CHS-ABS3 */
uint16_t Chs_Abs_GetTrimOffset(void)
{
    return g_chs_abs_cfg.trim_offset;
}

/* REQ-CHS-ABS3 */
void Chs_Abs_SetTrimOffset(uint16_t v)
{
    g_chs_abs_cfg.trim_offset = chs_abs_clamp_u16(v, 0xFFFFu);
}

/* REQ-CHS-ABS4 */
uint16_t Chs_Abs_ReadWheelFL(void)
{
    uint16_t raw = g_chs_abs_inputs[0];
    uint16_t out = chs_abs_scale(raw);
    g_chs_abs_state.raw = raw;
    return out;
}

/* REQ-CHS-ABS4 */
uint16_t Chs_Abs_ReadWheelFR(void)
{
    uint16_t raw = g_chs_abs_inputs[1];
    uint16_t out = chs_abs_scale(raw);
    g_chs_abs_state.raw = raw;
    return out;
}

/* REQ-CHS-ABS4 */
uint16_t Chs_Abs_ReadWheelRL(void)
{
    uint16_t raw = g_chs_abs_inputs[2];
    uint16_t out = chs_abs_scale(raw);
    g_chs_abs_state.raw = raw;
    return out;
}

/* REQ-CHS-ABS4 */
uint16_t Chs_Abs_ReadWheelRR(void)
{
    uint16_t raw = g_chs_abs_inputs[3];
    uint16_t out = chs_abs_scale(raw);
    g_chs_abs_state.raw = raw;
    return out;
}

/* REQ-CHS-ABS4 */
uint16_t Chs_Abs_ReadAux01(void)
{
    uint16_t raw = g_chs_abs_inputs[4];
    uint16_t out = chs_abs_scale(raw);
    g_chs_abs_state.raw = raw;
    return out;
}

/* REQ-CHS-ABS4 */
uint16_t Chs_Abs_ReadAux02(void)
{
    uint16_t raw = g_chs_abs_inputs[5];
    uint16_t out = chs_abs_scale(raw);
    g_chs_abs_state.raw = raw;
    return out;
}

/* REQ-CHS-ABS5 */
uint16_t Chs_Abs_Compute(void)
{
    uint16_t a = Chs_Abs_ReadWheelFL();
    uint16_t b = chs_abs_lpf(a, g_chs_abs_state.value);
    uint16_t c = chs_abs_clamp_u16(b, g_chs_abs_cfg.slip_thresh_pct);
    g_chs_abs_state.value = c;
    return c;
}

/* REQ-CHS-ABS6 */
uint8_t Chs_Abs_SelfTest(void)
{
    uint8_t crc = chs_abs_crc8((const uint8_t *)&g_chs_abs_cfg, (uint8_t)sizeof(Chs_Abs_Config_t));
    g_chs_abs_state.valid = (crc != 0u) ? 1u : 0u;
    return g_chs_abs_state.valid;
}

/* REQ-CHS-ABS7 */
void Chs_Abs_Step(void)
{
    g_chs_abs_state.phase = CHS_ABS_P_RUN;
    (void)Chs_Abs_Compute();
    if (g_chs_abs_state.value > g_chs_abs_cfg.slip_thresh_pct) {
        g_chs_abs_state.fault_count++;
        g_chs_abs_state.phase = CHS_ABS_P_FAULT;
    }
    if (Chs_Abs_SelfTest() == 0u) {
        g_chs_abs_state.phase = CHS_ABS_P_LIMP;
    }
}

/* REQ-CHS-ABS1 */
const Chs_Abs_State_t *Chs_Abs_GetState(void)
{
    return &g_chs_abs_state;
}
