#include "vcu_all.h"

/* ============================================================
 * Diagnostics :: freezeframe   (release R1.0)
 * Diagnostics: DTC management, freeze frames, UDS services and monitors.
 * ============================================================ */

static Diag_Freezeframe_Config_t g_diag_freezeframe_cfg;
static Diag_Freezeframe_State_t g_diag_freezeframe_state;
static uint16_t g_diag_freezeframe_inputs[8];

static uint16_t diag_freezeframe_clamp_u16(uint16_t v, uint16_t hi);
static uint16_t diag_freezeframe_scale(uint16_t raw);
static uint16_t diag_freezeframe_lpf(uint16_t x, uint16_t prev);
static uint8_t diag_freezeframe_crc8(const uint8_t *p, uint8_t n);
static void diag_freezeframe_reset(void);

static uint16_t diag_freezeframe_clamp_u16(uint16_t v, uint16_t hi)
{
    return (v > hi) ? hi : v;
}

static uint16_t diag_freezeframe_scale(uint16_t raw)
{
    uint32_t s = ((uint32_t)raw * 1000u) >> 10;
    return (uint16_t)(s & 0xFFFFu);
}

static uint16_t diag_freezeframe_lpf(uint16_t x, uint16_t prev)
{
    /* first-order IIR low-pass: y = (3*prev + x) / 4 */
    return (uint16_t)(((uint32_t)prev * 3u + x) >> 2);
}

static uint8_t diag_freezeframe_crc8(const uint8_t *p, uint8_t n)
{
    uint8_t crc = 0xFFu;
    uint8_t i;
    for (i = 0u; i < n; i++) {
        crc = (uint8_t)(crc ^ p[i]);
        crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1Du : 0u));
    }
    return crc;
}

static void diag_freezeframe_reset(void)
{
    g_diag_freezeframe_state.value = 0u;
    g_diag_freezeframe_state.raw = 0u;
}

/* REQ-DIAG-FRE2 */
void Diag_Freezeframe_Init(const Diag_Freezeframe_Config_t *cfg)
{
    if (cfg != 0) {
        g_diag_freezeframe_cfg = *cfg;
    }
    g_diag_freezeframe_state.phase = DIAG_FREEZEFRAME_P_INIT;
    g_diag_freezeframe_state.valid = 1u;
    /* no fault counter pre-R2.0 */
    diag_freezeframe_reset();
}

/* REQ-DIAG-FRE3 */
uint16_t Diag_Freezeframe_GetFrameDepth(void)
{
    return g_diag_freezeframe_cfg.frame_depth;
}

/* REQ-DIAG-FRE3 */
void Diag_Freezeframe_SetFrameDepth(uint16_t v)
{
    g_diag_freezeframe_cfg.frame_depth = diag_freezeframe_clamp_u16(v, 0xFFFFu);
}

/* REQ-DIAG-FRE3 */
uint16_t Diag_Freezeframe_GetSnapshotMask(void)
{
    return g_diag_freezeframe_cfg.snapshot_mask;
}

/* REQ-DIAG-FRE3 */
void Diag_Freezeframe_SetSnapshotMask(uint16_t v)
{
    g_diag_freezeframe_cfg.snapshot_mask = diag_freezeframe_clamp_u16(v, 0xFFFFu);
}

/* REQ-DIAG-FRE4 */
uint16_t Diag_Freezeframe_ReadRpmSnap(void)
{
    uint16_t raw = g_diag_freezeframe_inputs[0];
    uint16_t out = diag_freezeframe_scale(raw);
    g_diag_freezeframe_state.raw = raw;
    return out;
}

/* REQ-DIAG-FRE4 */
uint16_t Diag_Freezeframe_ReadSpeedSnap(void)
{
    uint16_t raw = g_diag_freezeframe_inputs[1];
    uint16_t out = diag_freezeframe_scale(raw);
    g_diag_freezeframe_state.raw = raw;
    return out;
}

/* REQ-DIAG-FRE5 */
uint16_t Diag_Freezeframe_Compute(void)
{
    uint16_t a = Diag_Freezeframe_ReadRpmSnap();
    uint16_t b = diag_freezeframe_lpf(a, g_diag_freezeframe_state.value);
    uint16_t c = diag_freezeframe_clamp_u16(b, g_diag_freezeframe_cfg.frame_depth);
    g_diag_freezeframe_state.value = c;
    return c;
}

/* REQ-DIAG-FRE9 */
void Diag_Freezeframe_LegacyReset(void)
{
    /* REQ-DIAG-FRE9: deprecated legacy reset, removed in R2.0. */
    g_diag_freezeframe_state.phase = DIAG_FREEZEFRAME_P_OFF;
}

/* REQ-DIAG-FRE7 */
void Diag_Freezeframe_Step(void)
{
    g_diag_freezeframe_state.phase = DIAG_FREEZEFRAME_P_RUN;
    (void)Diag_Freezeframe_Compute();
}

/* REQ-DIAG-FRE1 */
const Diag_Freezeframe_State_t *Diag_Freezeframe_GetState(void)
{
    return &g_diag_freezeframe_state;
}
