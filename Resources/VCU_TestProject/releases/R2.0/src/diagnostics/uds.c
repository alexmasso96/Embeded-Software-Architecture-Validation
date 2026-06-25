#include "vcu_all.h"

/* ============================================================
 * Diagnostics :: uds   (release R2.0)
 * Diagnostics: DTC management, freeze frames, UDS services and monitors.
 * ============================================================ */

static Diag_Uds_Config_t g_diag_uds_cfg;
static Diag_Uds_State_t g_diag_uds_state;
static uint16_t g_diag_uds_inputs[8];

static uint16_t diag_uds_clamp_u16(uint16_t v, uint16_t hi);
static uint16_t diag_uds_scale(uint16_t raw);
static uint16_t diag_uds_lpf(uint16_t x, uint16_t prev);
static uint8_t diag_uds_crc8(const uint8_t *p, uint8_t n);
static void diag_uds_reset(void);

static uint16_t diag_uds_clamp_u16(uint16_t v, uint16_t hi)
{
    return (v > hi) ? hi : v;
}

static uint16_t diag_uds_scale(uint16_t raw)
{
    uint32_t s = ((uint32_t)raw * 1000u) >> 10;
    return (uint16_t)(s & 0xFFFFu);
}

static uint16_t diag_uds_lpf(uint16_t x, uint16_t prev)
{
    /* first-order IIR low-pass: y = (3*prev + x) / 4 */
    return (uint16_t)(((uint32_t)prev * 3u + x) >> 2);
}

static uint8_t diag_uds_crc8(const uint8_t *p, uint8_t n)
{
    uint8_t crc = 0xFFu;
    uint8_t i;
    for (i = 0u; i < n; i++) {
        crc = (uint8_t)(crc ^ p[i]);
        crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1Du : 0u));
    }
    return crc;
}

static void diag_uds_reset(void)
{
    g_diag_uds_state.value = 0u;
    g_diag_uds_state.raw = 0u;
}

/* REQ-DIAG-UDS2 */
void Diag_Uds_Init(const Diag_Uds_Config_t *cfg)
{
    if (cfg != 0) {
        g_diag_uds_cfg = *cfg;
    }
    g_diag_uds_state.phase = DIAG_UDS_P_INIT;
    g_diag_uds_state.valid = 1u;
    g_diag_uds_state.fault_count = 0u;
    diag_uds_reset();
}

/* REQ-DIAG-UDS3 */
uint16_t Diag_Uds_GetP2TimeoutMs(void)
{
    return g_diag_uds_cfg.p2_timeout_ms;
}

/* REQ-DIAG-UDS3 */
void Diag_Uds_SetP2TimeoutMs(uint16_t v)
{
    g_diag_uds_cfg.p2_timeout_ms = diag_uds_clamp_u16(v, 0xFFFFu);
}

/* REQ-DIAG-UDS3 */
uint16_t Diag_Uds_GetS3TimeoutMs(void)
{
    return g_diag_uds_cfg.s3_timeout_ms;
}

/* REQ-DIAG-UDS3 */
void Diag_Uds_SetS3TimeoutMs(uint16_t v)
{
    g_diag_uds_cfg.s3_timeout_ms = diag_uds_clamp_u16(v, 0xFFFFu);
}

/* REQ-DIAG-UDS4 */
uint16_t Diag_Uds_ReadRxPending(void)
{
    uint16_t raw = g_diag_uds_inputs[0];
    uint16_t out = diag_uds_scale(raw);
    g_diag_uds_state.raw = raw;
    return out;
}

/* REQ-DIAG-UDS4 */
uint16_t Diag_Uds_ReadSessionType(void)
{
    uint16_t raw = g_diag_uds_inputs[1];
    uint16_t out = diag_uds_scale(raw);
    g_diag_uds_state.raw = raw;
    return out;
}

/* REQ-DIAG-UDS4 */
uint16_t Diag_Uds_ReadAux01(void)
{
    uint16_t raw = g_diag_uds_inputs[2];
    uint16_t out = diag_uds_scale(raw);
    g_diag_uds_state.raw = raw;
    return out;
}

/* REQ-DIAG-UDS5 */
uint16_t Diag_Uds_Compute(void)
{
    uint16_t a = Diag_Uds_ReadRxPending();
    uint16_t b = diag_uds_lpf(a, g_diag_uds_state.value);
    uint16_t c = diag_uds_clamp_u16(b, g_diag_uds_cfg.p2_timeout_ms);
    g_diag_uds_state.value = c;
    return c;
}

/* REQ-DIAG-UDS7 */
void Diag_Uds_Step(void)
{
    g_diag_uds_state.phase = DIAG_UDS_P_RUN;
    (void)Diag_Uds_Compute();
    if (g_diag_uds_state.value > g_diag_uds_cfg.p2_timeout_ms) {
        g_diag_uds_state.fault_count++;
        g_diag_uds_state.phase = DIAG_UDS_P_FAULT;
    }
}

/* REQ-DIAG-UDS1 */
const Diag_Uds_State_t *Diag_Uds_GetState(void)
{
    return &g_diag_uds_state;
}
