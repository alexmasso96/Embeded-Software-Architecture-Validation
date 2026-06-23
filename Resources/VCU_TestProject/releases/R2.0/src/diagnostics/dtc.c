#include "vcu_all.h"

/* ============================================================
 * Diagnostics :: dtc   (release R2.0)
 * Diagnostics: DTC management, freeze frames, UDS services and monitors.
 * ============================================================ */

static Diag_Dtc_Config_t g_diag_dtc_cfg;
static Diag_Dtc_State_t g_diag_dtc_state;
static uint16_t g_diag_dtc_inputs[8];

static uint16_t diag_dtc_clamp_u16(uint16_t v, uint16_t hi);
static uint16_t diag_dtc_scale(uint16_t raw);
static uint16_t diag_dtc_lpf(uint16_t x, uint16_t prev);
static uint8_t diag_dtc_crc8(const uint8_t *p, uint8_t n);
static void diag_dtc_reset(void);

static uint16_t diag_dtc_clamp_u16(uint16_t v, uint16_t hi)
{
    return (v > hi) ? hi : v;
}

static uint16_t diag_dtc_scale(uint16_t raw)
{
    uint32_t s = ((uint32_t)raw * 1000u) >> 10;
    return (uint16_t)(s & 0xFFFFu);
}

static uint16_t diag_dtc_lpf(uint16_t x, uint16_t prev)
{
    /* first-order IIR low-pass: y = (3*prev + x) / 4 */
    return (uint16_t)(((uint32_t)prev * 3u + x) >> 2);
}

static uint8_t diag_dtc_crc8(const uint8_t *p, uint8_t n)
{
    uint8_t crc = 0xFFu;
    uint8_t i;
    for (i = 0u; i < n; i++) {
        crc = (uint8_t)(crc ^ p[i]);
        crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1Du : 0u));
    }
    return crc;
}

static void diag_dtc_reset(void)
{
    g_diag_dtc_state.value = 0u;
    g_diag_dtc_state.raw = 0u;
}

/* REQ-DIAG-DTC2 */
void Diag_Dtc_Init(const Diag_Dtc_Config_t *cfg)
{
    if (cfg != 0) {
        g_diag_dtc_cfg = *cfg;
    }
    g_diag_dtc_state.phase = DIAG_DTC_P_INIT;
    g_diag_dtc_state.valid = 1u;
    g_diag_dtc_state.fault_count = 0u;
    diag_dtc_reset();
}

/* REQ-DIAG-DTC3 */
uint16_t Diag_Dtc_GetAgingThreshold(void)
{
    return g_diag_dtc_cfg.aging_threshold;
}

/* REQ-DIAG-DTC3 */
void Diag_Dtc_SetAgingThreshold(uint16_t v)
{
    g_diag_dtc_cfg.aging_threshold = diag_dtc_clamp_u16(v, 0xFFFFu);
}

/* REQ-DIAG-DTC3 */
uint16_t Diag_Dtc_GetConfirmCycles(void)
{
    return g_diag_dtc_cfg.confirm_cycles;
}

/* REQ-DIAG-DTC3 */
void Diag_Dtc_SetConfirmCycles(uint16_t v)
{
    g_diag_dtc_cfg.confirm_cycles = diag_dtc_clamp_u16(v, 0xFFFFu);
}

/* REQ-DIAG-DTC4 */
uint16_t Diag_Dtc_ReadFaultBits(void)
{
    uint16_t raw = g_diag_dtc_inputs[0];
    uint16_t out = diag_dtc_scale(raw);
    g_diag_dtc_state.raw = raw;
    return out;
}

/* REQ-DIAG-DTC4 */
uint16_t Diag_Dtc_ReadIgnCycle(void)
{
    uint16_t raw = g_diag_dtc_inputs[1];
    uint16_t out = diag_dtc_scale(raw);
    g_diag_dtc_state.raw = raw;
    return out;
}

/* REQ-DIAG-DTC4 */
uint16_t Diag_Dtc_ReadAux01(void)
{
    uint16_t raw = g_diag_dtc_inputs[2];
    uint16_t out = diag_dtc_scale(raw);
    g_diag_dtc_state.raw = raw;
    return out;
}

/* REQ-DIAG-DTC5 */
uint16_t Diag_Dtc_Compute(void)
{
    uint16_t a = Diag_Dtc_ReadFaultBits();
    uint16_t b = diag_dtc_lpf(a, g_diag_dtc_state.value);
    uint16_t c = diag_dtc_clamp_u16(b, g_diag_dtc_cfg.aging_threshold);
    g_diag_dtc_state.value = c;
    return c;
}

/* REQ-DIAG-DTC7 */
void Diag_Dtc_Step(void)
{
    g_diag_dtc_state.phase = DIAG_DTC_P_RUN;
    (void)Diag_Dtc_Compute();
    if (g_diag_dtc_state.value > g_diag_dtc_cfg.aging_threshold) {
        g_diag_dtc_state.fault_count++;
        g_diag_dtc_state.phase = DIAG_DTC_P_FAULT;
    }
}

/* REQ-DIAG-DTC1 */
const Diag_Dtc_State_t *Diag_Dtc_GetState(void)
{
    return &g_diag_dtc_state;
}
