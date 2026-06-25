#include "vcu_all.h"

/* ============================================================
 * ChassisControl :: traction   (release R3.0)
 * Chassis Control (introduced R2.0): ABS, traction, steering assist and suspension.
 * ============================================================ */

static Chs_Traction_Config_t g_chs_traction_cfg;
static Chs_Traction_State_t g_chs_traction_state;
static uint16_t g_chs_traction_inputs[8];

static uint16_t chs_traction_clamp_u16(uint16_t v, uint16_t hi);
static uint16_t chs_traction_scale(uint16_t raw);
static uint16_t chs_traction_lpf(uint16_t x, uint16_t prev);
static uint8_t chs_traction_crc8(const uint8_t *p, uint8_t n);
static void chs_traction_reset(void);

static uint16_t chs_traction_clamp_u16(uint16_t v, uint16_t hi)
{
    return (v > hi) ? hi : v;
}

static uint16_t chs_traction_scale(uint16_t raw)
{
    uint32_t s = ((uint32_t)raw * 1000u) >> 10;
    return (uint16_t)(s & 0xFFFFu);
}

static uint16_t chs_traction_lpf(uint16_t x, uint16_t prev)
{
    /* first-order IIR low-pass: y = (3*prev + x) / 4 */
    return (uint16_t)(((uint32_t)prev * 3u + x) >> 2);
}

static uint8_t chs_traction_crc8(const uint8_t *p, uint8_t n)
{
    uint8_t crc = 0xFFu;
    uint8_t i;
    for (i = 0u; i < n; i++) {
        crc = (uint8_t)(crc ^ p[i]);
        crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1Du : 0u));
    }
    return crc;
}

static void chs_traction_reset(void)
{
    g_chs_traction_state.value = 0u;
    g_chs_traction_state.raw = 0u;
}

/* REQ-CHS-TRA2 */
void Chs_Traction_Init(const Chs_Traction_Config_t *cfg)
{
    if (cfg != 0) {
        g_chs_traction_cfg = *cfg;
    }
    g_chs_traction_state.phase = CHS_TRACTION_P_INIT;
    g_chs_traction_state.valid = 1u;
    g_chs_traction_state.fault_count = 0u;
    chs_traction_reset();
}

/* REQ-CHS-TRA3 */
uint16_t Chs_Traction_GetTcSlipPct(void)
{
    return g_chs_traction_cfg.tc_slip_pct;
}

/* REQ-CHS-TRA3 */
void Chs_Traction_SetTcSlipPct(uint16_t v)
{
    g_chs_traction_cfg.tc_slip_pct = chs_traction_clamp_u16(v, 0xFFFFu);
}

/* REQ-CHS-TRA3 */
uint16_t Chs_Traction_GetTorqueCutNm(void)
{
    return g_chs_traction_cfg.torque_cut_nm;
}

/* REQ-CHS-TRA3 */
void Chs_Traction_SetTorqueCutNm(uint16_t v)
{
    g_chs_traction_cfg.torque_cut_nm = chs_traction_clamp_u16(v, 0xFFFFu);
}

/* REQ-CHS-TRA3 */
uint16_t Chs_Traction_GetTrimOffset(void)
{
    return g_chs_traction_cfg.trim_offset;
}

/* REQ-CHS-TRA3 */
void Chs_Traction_SetTrimOffset(uint16_t v)
{
    g_chs_traction_cfg.trim_offset = chs_traction_clamp_u16(v, 0xFFFFu);
}

/* REQ-CHS-TRA4 */
uint16_t Chs_Traction_ReadDriveSlip(void)
{
    uint16_t raw = g_chs_traction_inputs[0];
    uint16_t out = chs_traction_scale(raw);
    g_chs_traction_state.raw = raw;
    return out;
}

/* REQ-CHS-TRA4 */
uint16_t Chs_Traction_ReadYaw(void)
{
    uint16_t raw = g_chs_traction_inputs[1];
    uint16_t out = chs_traction_scale(raw);
    g_chs_traction_state.raw = raw;
    return out;
}

/* REQ-CHS-TRA4 */
uint16_t Chs_Traction_ReadAux01(void)
{
    uint16_t raw = g_chs_traction_inputs[2];
    uint16_t out = chs_traction_scale(raw);
    g_chs_traction_state.raw = raw;
    return out;
}

/* REQ-CHS-TRA4 */
uint16_t Chs_Traction_ReadAux02(void)
{
    uint16_t raw = g_chs_traction_inputs[3];
    uint16_t out = chs_traction_scale(raw);
    g_chs_traction_state.raw = raw;
    return out;
}

/* REQ-CHS-TRA5 */
uint16_t Chs_Traction_Compute(void)
{
    uint16_t a = Chs_Traction_ReadDriveSlip();
    uint16_t b = chs_traction_lpf(a, g_chs_traction_state.value);
    uint16_t c = chs_traction_clamp_u16(b, g_chs_traction_cfg.tc_slip_pct);
    g_chs_traction_state.value = c;
    return c;
}

/* REQ-CHS-TRA6 */
uint8_t Chs_Traction_SelfTest(void)
{
    uint8_t crc = chs_traction_crc8((const uint8_t *)&g_chs_traction_cfg, (uint8_t)sizeof(Chs_Traction_Config_t));
    g_chs_traction_state.valid = (crc != 0u) ? 1u : 0u;
    return g_chs_traction_state.valid;
}

/* REQ-CHS-TRA7 */
void Chs_Traction_Step(void)
{
    g_chs_traction_state.phase = CHS_TRACTION_P_RUN;
    (void)Chs_Traction_Compute();
    if (g_chs_traction_state.value > g_chs_traction_cfg.tc_slip_pct) {
        g_chs_traction_state.fault_count++;
        g_chs_traction_state.phase = CHS_TRACTION_P_FAULT;
    }
    if (Chs_Traction_SelfTest() == 0u) {
        g_chs_traction_state.phase = CHS_TRACTION_P_LIMP;
    }
}

/* REQ-CHS-TRA1 */
const Chs_Traction_State_t *Chs_Traction_GetState(void)
{
    return &g_chs_traction_state;
}
