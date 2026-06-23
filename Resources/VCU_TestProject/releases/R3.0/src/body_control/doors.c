#include "vcu_all.h"

/* ============================================================
 * BodyControl :: doors   (release R3.0)
 * Body Control Module: exterior/interior lighting, doors, wipers, windows and mirrors.
 * ============================================================ */

static Bcm_Doors_Config_t g_bcm_doors_cfg;
static Bcm_Doors_State_t g_bcm_doors_state;
static uint16_t g_bcm_doors_inputs[8];

static uint16_t bcm_doors_clamp_u16(uint16_t v, uint16_t hi);
static uint16_t bcm_doors_scale(uint16_t raw);
static uint16_t bcm_doors_lpf(uint16_t x, uint16_t prev);
static uint8_t bcm_doors_crc8(const uint8_t *p, uint8_t n);
static void bcm_doors_reset(void);

static uint16_t bcm_doors_clamp_u16(uint16_t v, uint16_t hi)
{
    return (v > hi) ? hi : v;
}

static uint16_t bcm_doors_scale(uint16_t raw)
{
    uint32_t s = ((uint32_t)raw * 1000u) >> 10;
    return (uint16_t)(s & 0xFFFFu);
}

static uint16_t bcm_doors_lpf(uint16_t x, uint16_t prev)
{
    /* first-order IIR low-pass: y = (3*prev + x) / 4 */
    return (uint16_t)(((uint32_t)prev * 3u + x) >> 2);
}

static uint8_t bcm_doors_crc8(const uint8_t *p, uint8_t n)
{
    uint8_t crc = 0xFFu;
    uint8_t i;
    for (i = 0u; i < n; i++) {
        crc = (uint8_t)(crc ^ p[i]);
        crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1Du : 0u));
    }
    return crc;
}

static void bcm_doors_reset(void)
{
    g_bcm_doors_state.value = 0u;
    g_bcm_doors_state.raw = 0u;
}

/* REQ-BCM-DOO2 */
void Bcm_Doors_Init(const Bcm_Doors_Config_t *cfg)
{
    if (cfg != 0) {
        g_bcm_doors_cfg = *cfg;
    }
    g_bcm_doors_state.phase = BCM_DOORS_P_INIT;
    g_bcm_doors_state.valid = 1u;
    g_bcm_doors_state.fault_count = 0u;
    bcm_doors_reset();
}

/* REQ-BCM-DOO3 */
uint16_t Bcm_Doors_GetLockTimeoutMs(void)
{
    return g_bcm_doors_cfg.lock_timeout_ms;
}

/* REQ-BCM-DOO3 */
void Bcm_Doors_SetLockTimeoutMs(uint16_t v)
{
    g_bcm_doors_cfg.lock_timeout_ms = bcm_doors_clamp_u16(v, 0xFFFFu);
}

/* REQ-BCM-DOO3 */
uint16_t Bcm_Doors_GetAjarDebounce(void)
{
    return g_bcm_doors_cfg.ajar_debounce;
}

/* REQ-BCM-DOO3 */
void Bcm_Doors_SetAjarDebounce(uint16_t v)
{
    g_bcm_doors_cfg.ajar_debounce = bcm_doors_clamp_u16(v, 0xFFFFu);
}

/* REQ-BCM-DOO3 */
uint16_t Bcm_Doors_GetTrimOffset(void)
{
    return g_bcm_doors_cfg.trim_offset;
}

/* REQ-BCM-DOO3 */
void Bcm_Doors_SetTrimOffset(uint16_t v)
{
    g_bcm_doors_cfg.trim_offset = bcm_doors_clamp_u16(v, 0xFFFFu);
}

/* REQ-BCM-DOO4 */
uint16_t Bcm_Doors_ReadLatchState(void)
{
    uint16_t raw = g_bcm_doors_inputs[0];
    uint16_t out = bcm_doors_scale(raw);
    g_bcm_doors_state.raw = raw;
    return out;
}

/* REQ-BCM-DOO4 */
uint16_t Bcm_Doors_ReadHandlePull(void)
{
    uint16_t raw = g_bcm_doors_inputs[1];
    uint16_t out = bcm_doors_scale(raw);
    g_bcm_doors_state.raw = raw;
    return out;
}

/* REQ-BCM-DOO4 */
uint16_t Bcm_Doors_ReadLockBtn(void)
{
    uint16_t raw = g_bcm_doors_inputs[2];
    uint16_t out = bcm_doors_scale(raw);
    g_bcm_doors_state.raw = raw;
    return out;
}

/* REQ-BCM-DOO4 */
uint16_t Bcm_Doors_ReadAux01(void)
{
    uint16_t raw = g_bcm_doors_inputs[3];
    uint16_t out = bcm_doors_scale(raw);
    g_bcm_doors_state.raw = raw;
    return out;
}

/* REQ-BCM-DOO4 */
uint16_t Bcm_Doors_ReadAux02(void)
{
    uint16_t raw = g_bcm_doors_inputs[4];
    uint16_t out = bcm_doors_scale(raw);
    g_bcm_doors_state.raw = raw;
    return out;
}

/* REQ-BCM-DOO5 */
uint16_t Bcm_Doors_Compute(void)
{
    uint16_t a = Bcm_Doors_ReadLatchState();
    uint16_t b = bcm_doors_lpf(a, g_bcm_doors_state.value);
    uint16_t c = bcm_doors_clamp_u16(b, g_bcm_doors_cfg.lock_timeout_ms);
    g_bcm_doors_state.value = c;
    return c;
}

/* REQ-BCM-DOO6 */
uint8_t Bcm_Doors_SelfTest(void)
{
    uint8_t crc = bcm_doors_crc8((const uint8_t *)&g_bcm_doors_cfg, (uint8_t)sizeof(Bcm_Doors_Config_t));
    g_bcm_doors_state.valid = (crc != 0u) ? 1u : 0u;
    return g_bcm_doors_state.valid;
}

/* REQ-BCM-DOO7 */
void Bcm_Doors_Step(void)
{
    g_bcm_doors_state.phase = BCM_DOORS_P_RUN;
    (void)Bcm_Doors_Compute();
    if (g_bcm_doors_state.value > g_bcm_doors_cfg.lock_timeout_ms) {
        g_bcm_doors_state.fault_count++;
        g_bcm_doors_state.phase = BCM_DOORS_P_FAULT;
    }
    if (Bcm_Doors_SelfTest() == 0u) {
        g_bcm_doors_state.phase = BCM_DOORS_P_LIMP;
    }
}

/* REQ-BCM-DOO1 */
const Bcm_Doors_State_t *Bcm_Doors_GetState(void)
{
    return &g_bcm_doors_state;
}
