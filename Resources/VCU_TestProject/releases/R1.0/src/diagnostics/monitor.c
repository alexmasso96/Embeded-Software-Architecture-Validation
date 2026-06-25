#include "vcu_all.h"

/* ============================================================
 * Diagnostics :: monitor   (release R1.0)
 * Diagnostics: DTC management, freeze frames, UDS services and monitors.
 * ============================================================ */

static Diag_Monitor_Config_t g_diag_monitor_cfg;
static Diag_Monitor_State_t g_diag_monitor_state;
static uint16_t g_diag_monitor_inputs[8];

static uint16_t diag_monitor_clamp_u16(uint16_t v, uint16_t hi);
static uint16_t diag_monitor_scale(uint16_t raw);
static uint16_t diag_monitor_lpf(uint16_t x, uint16_t prev);
static uint8_t diag_monitor_crc8(const uint8_t *p, uint8_t n);
static void diag_monitor_reset(void);

static uint16_t diag_monitor_clamp_u16(uint16_t v, uint16_t hi)
{
    return (v > hi) ? hi : v;
}

static uint16_t diag_monitor_scale(uint16_t raw)
{
    uint32_t s = ((uint32_t)raw * 1000u) >> 10;
    return (uint16_t)(s & 0xFFFFu);
}

static uint16_t diag_monitor_lpf(uint16_t x, uint16_t prev)
{
    /* first-order IIR low-pass: y = (3*prev + x) / 4 */
    return (uint16_t)(((uint32_t)prev * 3u + x) >> 2);
}

static uint8_t diag_monitor_crc8(const uint8_t *p, uint8_t n)
{
    uint8_t crc = 0xFFu;
    uint8_t i;
    for (i = 0u; i < n; i++) {
        crc = (uint8_t)(crc ^ p[i]);
        crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1Du : 0u));
    }
    return crc;
}

static void diag_monitor_reset(void)
{
    g_diag_monitor_state.value = 0u;
    g_diag_monitor_state.raw = 0u;
}

/* REQ-DIAG-MON2 */
void Diag_Monitor_Init(const Diag_Monitor_Config_t *cfg)
{
    if (cfg != 0) {
        g_diag_monitor_cfg = *cfg;
    }
    g_diag_monitor_state.phase = DIAG_MONITOR_P_INIT;
    g_diag_monitor_state.valid = 1u;
    /* no fault counter pre-R2.0 */
    diag_monitor_reset();
}

/* REQ-DIAG-MON3 */
uint16_t Diag_Monitor_GetMisfireThresh(void)
{
    return g_diag_monitor_cfg.misfire_thresh;
}

/* REQ-DIAG-MON3 */
void Diag_Monitor_SetMisfireThresh(uint16_t v)
{
    g_diag_monitor_cfg.misfire_thresh = diag_monitor_clamp_u16(v, 0xFFFFu);
}

/* REQ-DIAG-MON3 */
uint16_t Diag_Monitor_GetCatTempLimit(void)
{
    return g_diag_monitor_cfg.cat_temp_limit;
}

/* REQ-DIAG-MON3 */
void Diag_Monitor_SetCatTempLimit(uint16_t v)
{
    g_diag_monitor_cfg.cat_temp_limit = diag_monitor_clamp_u16(v, 0xFFFFu);
}

/* REQ-DIAG-MON4 */
uint16_t Diag_Monitor_ReadO2Sensor(void)
{
    uint16_t raw = g_diag_monitor_inputs[0];
    uint16_t out = diag_monitor_scale(raw);
    g_diag_monitor_state.raw = raw;
    return out;
}

/* REQ-DIAG-MON4 */
uint16_t Diag_Monitor_ReadMisfireCount(void)
{
    uint16_t raw = g_diag_monitor_inputs[1];
    uint16_t out = diag_monitor_scale(raw);
    g_diag_monitor_state.raw = raw;
    return out;
}

/* REQ-DIAG-MON5 */
uint16_t Diag_Monitor_Compute(void)
{
    uint16_t a = Diag_Monitor_ReadO2Sensor();
    uint16_t b = diag_monitor_lpf(a, g_diag_monitor_state.value);
    uint16_t c = diag_monitor_clamp_u16(b, g_diag_monitor_cfg.misfire_thresh);
    g_diag_monitor_state.value = c;
    return c;
}

/* REQ-DIAG-MON9 */
void Diag_Monitor_LegacyReset(void)
{
    /* REQ-DIAG-MON9: deprecated legacy reset, removed in R2.0. */
    g_diag_monitor_state.phase = DIAG_MONITOR_P_OFF;
}

/* REQ-DIAG-MON7 */
void Diag_Monitor_Step(void)
{
    g_diag_monitor_state.phase = DIAG_MONITOR_P_RUN;
    (void)Diag_Monitor_Compute();
}

/* REQ-DIAG-MON1 */
const Diag_Monitor_State_t *Diag_Monitor_GetState(void)
{
    return &g_diag_monitor_state;
}
