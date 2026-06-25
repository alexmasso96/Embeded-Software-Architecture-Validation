#include "vcu_all.h"

/* ============================================================
 * ChargingCtrl :: acdc   (release R3.0)
 * Charging Control (introduced R3.0): AC/DC charging state machine, control pilot and metering.
 * ============================================================ */

static Chg_Acdc_Config_t g_chg_acdc_cfg;
static Chg_Acdc_State_t g_chg_acdc_state;
static uint16_t g_chg_acdc_inputs[8];

static uint16_t chg_acdc_clamp_u16(uint16_t v, uint16_t hi);
static uint16_t chg_acdc_scale(uint16_t raw);
static uint16_t chg_acdc_lpf(uint16_t x, uint16_t prev);
static uint8_t chg_acdc_crc8(const uint8_t *p, uint8_t n);
static void chg_acdc_reset(void);

static uint16_t chg_acdc_clamp_u16(uint16_t v, uint16_t hi)
{
    return (v > hi) ? hi : v;
}

static uint16_t chg_acdc_scale(uint16_t raw)
{
    uint32_t s = ((uint32_t)raw * 1000u) >> 10;
    return (uint16_t)(s & 0xFFFFu);
}

static uint16_t chg_acdc_lpf(uint16_t x, uint16_t prev)
{
    /* first-order IIR low-pass: y = (3*prev + x) / 4 */
    return (uint16_t)(((uint32_t)prev * 3u + x) >> 2);
}

static uint8_t chg_acdc_crc8(const uint8_t *p, uint8_t n)
{
    uint8_t crc = 0xFFu;
    uint8_t i;
    for (i = 0u; i < n; i++) {
        crc = (uint8_t)(crc ^ p[i]);
        crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1Du : 0u));
    }
    return crc;
}

static void chg_acdc_reset(void)
{
    g_chg_acdc_state.value = 0u;
    g_chg_acdc_state.raw = 0u;
}

/* REQ-CHG-ACD2 */
void Chg_Acdc_Init(const Chg_Acdc_Config_t *cfg)
{
    if (cfg != 0) {
        g_chg_acdc_cfg = *cfg;
    }
    g_chg_acdc_state.phase = CHG_ACDC_P_INIT;
    g_chg_acdc_state.valid = 1u;
    g_chg_acdc_state.fault_count = 0u;
    chg_acdc_reset();
}

/* REQ-CHG-ACD3 */
uint16_t Chg_Acdc_GetMaxAmpsAc(void)
{
    return g_chg_acdc_cfg.max_amps_ac;
}

/* REQ-CHG-ACD3 */
void Chg_Acdc_SetMaxAmpsAc(uint16_t v)
{
    g_chg_acdc_cfg.max_amps_ac = chg_acdc_clamp_u16(v, 0xFFFFu);
}

/* REQ-CHG-ACD3 */
uint16_t Chg_Acdc_GetMaxAmpsDc(void)
{
    return g_chg_acdc_cfg.max_amps_dc;
}

/* REQ-CHG-ACD3 */
void Chg_Acdc_SetMaxAmpsDc(uint16_t v)
{
    g_chg_acdc_cfg.max_amps_dc = chg_acdc_clamp_u16(v, 0xFFFFu);
}

/* REQ-CHG-ACD3 */
uint16_t Chg_Acdc_GetTrimOffset(void)
{
    return g_chg_acdc_cfg.trim_offset;
}

/* REQ-CHG-ACD3 */
void Chg_Acdc_SetTrimOffset(uint16_t v)
{
    g_chg_acdc_cfg.trim_offset = chg_acdc_clamp_u16(v, 0xFFFFu);
}

/* REQ-CHG-ACD4 */
uint16_t Chg_Acdc_ReadPlugState(void)
{
    uint16_t raw = g_chg_acdc_inputs[0];
    uint16_t out = chg_acdc_scale(raw);
    g_chg_acdc_state.raw = raw;
    return out;
}

/* REQ-CHG-ACD4 */
uint16_t Chg_Acdc_ReadGridVolt(void)
{
    uint16_t raw = g_chg_acdc_inputs[1];
    uint16_t out = chg_acdc_scale(raw);
    g_chg_acdc_state.raw = raw;
    return out;
}

/* REQ-CHG-ACD4 */
uint16_t Chg_Acdc_ReadPilotPwm(void)
{
    uint16_t raw = g_chg_acdc_inputs[2];
    uint16_t out = chg_acdc_scale(raw);
    g_chg_acdc_state.raw = raw;
    return out;
}

/* REQ-CHG-ACD4 */
uint16_t Chg_Acdc_ReadAux01(void)
{
    uint16_t raw = g_chg_acdc_inputs[3];
    uint16_t out = chg_acdc_scale(raw);
    g_chg_acdc_state.raw = raw;
    return out;
}

/* REQ-CHG-ACD4 */
uint16_t Chg_Acdc_ReadAux02(void)
{
    uint16_t raw = g_chg_acdc_inputs[4];
    uint16_t out = chg_acdc_scale(raw);
    g_chg_acdc_state.raw = raw;
    return out;
}

/* REQ-CHG-ACD5 */
uint16_t Chg_Acdc_Compute(void)
{
    uint16_t a = Chg_Acdc_ReadPlugState();
    uint16_t b = chg_acdc_lpf(a, g_chg_acdc_state.value);
    uint16_t c = chg_acdc_clamp_u16(b, g_chg_acdc_cfg.max_amps_ac);
    g_chg_acdc_state.value = c;
    return c;
}

/* REQ-CHG-ACD6 */
uint8_t Chg_Acdc_SelfTest(void)
{
    uint8_t crc = chg_acdc_crc8((const uint8_t *)&g_chg_acdc_cfg, (uint8_t)sizeof(Chg_Acdc_Config_t));
    g_chg_acdc_state.valid = (crc != 0u) ? 1u : 0u;
    return g_chg_acdc_state.valid;
}

/* REQ-CHG-ACD7 */
void Chg_Acdc_Step(void)
{
    g_chg_acdc_state.phase = CHG_ACDC_P_RUN;
    (void)Chg_Acdc_Compute();
    if (g_chg_acdc_state.value > g_chg_acdc_cfg.max_amps_ac) {
        g_chg_acdc_state.fault_count++;
        g_chg_acdc_state.phase = CHG_ACDC_P_FAULT;
    }
    if (Chg_Acdc_SelfTest() == 0u) {
        g_chg_acdc_state.phase = CHG_ACDC_P_LIMP;
    }
}

/* REQ-CHG-ACD1 */
const Chg_Acdc_State_t *Chg_Acdc_GetState(void)
{
    return &g_chg_acdc_state;
}
