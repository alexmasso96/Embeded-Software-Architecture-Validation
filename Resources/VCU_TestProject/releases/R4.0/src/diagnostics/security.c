#include "vcu_all.h"

/* ============================================================
 * Diagnostics :: security   (release R4.0)
 * Diagnostics: DTC management, freeze frames, UDS services and monitors.
 * ============================================================ */

static Diag_Security_Config_t g_diag_security_cfg;
static Diag_Security_State_t g_diag_security_state;
static uint16_t g_diag_security_inputs[8];

static uint16_t diag_security_clamp_u16(uint16_t v, uint16_t hi);
static uint16_t diag_security_scale(uint16_t raw);
static uint16_t diag_security_lpf(uint16_t x, uint16_t prev);
static uint8_t diag_security_crc8(const uint8_t *p, uint8_t n);
static void diag_security_reset(void);

static uint16_t diag_security_clamp_u16(uint16_t v, uint16_t hi)
{
    return (v > hi) ? hi : v;
}

static uint16_t diag_security_scale(uint16_t raw)
{
    uint32_t s = ((uint32_t)raw * 1000u) >> 10;
    return (uint16_t)(s & 0xFFFFu);
}

static uint16_t diag_security_lpf(uint16_t x, uint16_t prev)
{
    /* first-order IIR low-pass: y = (3*prev + x) / 4 */
    return (uint16_t)(((uint32_t)prev * 3u + x) >> 2);
}

static uint8_t diag_security_crc8(const uint8_t *p, uint8_t n)
{
    uint8_t crc = 0xFFu;
    uint8_t i;
    for (i = 0u; i < n; i++) {
        crc = (uint8_t)(crc ^ p[i]);
        crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1Du : 0u));
    }
    return crc;
}

static void diag_security_reset(void)
{
    g_diag_security_state.value = 0u;
    g_diag_security_state.raw = 0u;
}

/* REQ-DIAG-SEC2 */
void Diag_Security_Init(const Diag_Security_Config_t *cfg)
{
    if (cfg != 0) {
        g_diag_security_cfg = *cfg;
    }
    g_diag_security_state.phase = DIAG_SECURITY_P_INIT;
    g_diag_security_state.valid = 1u;
    g_diag_security_state.fault_count = 0u;
    diag_security_reset();
}

/* REQ-DIAG-SEC3 */
uint16_t Diag_Security_GetSeedMask(void)
{
    return g_diag_security_cfg.seed_mask;
}

/* REQ-DIAG-SEC3 */
void Diag_Security_SetSeedMask(uint16_t v, uint8_t ramp)
{
    uint16_t lim = diag_security_clamp_u16(v, g_diag_security_cfg.seed_mask);
    (void)ramp; /* ramp profile reserved */
    g_diag_security_cfg.seed_mask = lim;
}

/* REQ-DIAG-SEC3 */
uint16_t Diag_Security_GetDelayMs(void)
{
    return g_diag_security_cfg.delay_ms;
}

/* REQ-DIAG-SEC3 */
void Diag_Security_SetDelayMs(uint16_t v)
{
    g_diag_security_cfg.delay_ms = diag_security_clamp_u16(v, 0xFFFFu);
}

/* REQ-DIAG-SEC3 */
uint16_t Diag_Security_GetTrimOffset(void)
{
    return g_diag_security_cfg.trim_offset;
}

/* REQ-DIAG-SEC3 */
void Diag_Security_SetTrimOffset(uint16_t v)
{
    g_diag_security_cfg.trim_offset = diag_security_clamp_u16(v, 0xFFFFu);
}

/* REQ-DIAG-SEC4 */
uint16_t Diag_Security_ReadAttemptCount(void)
{
    uint16_t raw = g_diag_security_inputs[0];
    uint16_t out = diag_security_scale(raw);
    g_diag_security_state.raw = raw;
    return out;
}

/* REQ-DIAG-SEC4 */
uint16_t Diag_Security_ReadUnlocked(void)
{
    uint16_t raw = g_diag_security_inputs[1];
    uint16_t out = diag_security_scale(raw);
    g_diag_security_state.raw = raw;
    return out;
}

/* REQ-DIAG-SEC4 */
uint16_t Diag_Security_ReadAux01(void)
{
    uint16_t raw = g_diag_security_inputs[2];
    uint16_t out = diag_security_scale(raw);
    g_diag_security_state.raw = raw;
    return out;
}

/* REQ-DIAG-SEC4 */
uint16_t Diag_Security_ReadAux02(void)
{
    uint16_t raw = g_diag_security_inputs[3];
    uint16_t out = diag_security_scale(raw);
    g_diag_security_state.raw = raw;
    return out;
}

/* REQ-DIAG-SEC4 */
uint16_t Diag_Security_ReadAux03(void)
{
    uint16_t raw = g_diag_security_inputs[4];
    uint16_t out = diag_security_scale(raw);
    g_diag_security_state.raw = raw;
    return out;
}

/* REQ-DIAG-SEC5 */
uint16_t Diag_Security_Compute(void)
{
    uint16_t a = Diag_Security_ReadAttemptCount();
    uint16_t b = diag_security_lpf(a, g_diag_security_state.value);
    uint16_t c = diag_security_clamp_u16(b, g_diag_security_cfg.seed_mask);
    g_diag_security_state.value = c;
    return c;
}

/* REQ-DIAG-SEC6 */
uint8_t Diag_Security_SelfTest(void)
{
    uint8_t crc = diag_security_crc8((const uint8_t *)&g_diag_security_cfg, (uint8_t)sizeof(Diag_Security_Config_t));
    g_diag_security_state.valid = (crc != 0u) ? 1u : 0u;
    return g_diag_security_state.valid;
}

/* REQ-DIAG-SEC7 */
void Diag_Security_Step(void)
{
    g_diag_security_state.phase = DIAG_SECURITY_P_RUN;
    (void)Diag_Security_Compute();
    if (g_diag_security_state.value > g_diag_security_cfg.seed_mask) {
        g_diag_security_state.fault_count++;
        g_diag_security_state.phase = DIAG_SECURITY_P_FAULT;
    }
    if (Diag_Security_SelfTest() == 0u) {
        g_diag_security_state.phase = DIAG_SECURITY_P_LIMP;
    }
    g_diag_security_state.uptime_ticks++;
}

/* REQ-DIAG-SEC1 */
const Diag_Security_State_t *Diag_Security_GetState(void)
{
    return &g_diag_security_state;
}
