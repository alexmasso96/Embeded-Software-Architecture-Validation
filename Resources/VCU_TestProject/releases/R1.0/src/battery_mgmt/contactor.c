#include "vcu_all.h"

/* ============================================================
 * BatteryMgmt :: contactor   (release R1.0)
 * Battery Management System: cell monitoring, state of charge, balancing and contactor control.
 * ============================================================ */

static Bms_Contactor_Config_t g_bms_contactor_cfg;
static Bms_Contactor_State_t g_bms_contactor_state;
static uint16_t g_bms_contactor_inputs[8];

static uint16_t bms_contactor_clamp_u16(uint16_t v, uint16_t hi);
static uint16_t bms_contactor_scale(uint16_t raw);
static uint16_t bms_contactor_lpf(uint16_t x, uint16_t prev);
static uint8_t bms_contactor_crc8(const uint8_t *p, uint8_t n);
static void bms_contactor_reset(void);

static uint16_t bms_contactor_clamp_u16(uint16_t v, uint16_t hi)
{
    return (v > hi) ? hi : v;
}

static uint16_t bms_contactor_scale(uint16_t raw)
{
    uint32_t s = ((uint32_t)raw * 1000u) >> 10;
    return (uint16_t)(s & 0xFFFFu);
}

static uint16_t bms_contactor_lpf(uint16_t x, uint16_t prev)
{
    /* first-order IIR low-pass: y = (3*prev + x) / 4 */
    return (uint16_t)(((uint32_t)prev * 3u + x) >> 2);
}

static uint8_t bms_contactor_crc8(const uint8_t *p, uint8_t n)
{
    uint8_t crc = 0xFFu;
    uint8_t i;
    for (i = 0u; i < n; i++) {
        crc = (uint8_t)(crc ^ p[i]);
        crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1Du : 0u));
    }
    return crc;
}

static void bms_contactor_reset(void)
{
    g_bms_contactor_state.value = 0u;
    g_bms_contactor_state.raw = 0u;
}

/* REQ-BMS-CON2 */
void Bms_Contactor_Init(const Bms_Contactor_Config_t *cfg)
{
    if (cfg != 0) {
        g_bms_contactor_cfg = *cfg;
    }
    g_bms_contactor_state.phase = BMS_CONTACTOR_P_INIT;
    g_bms_contactor_state.valid = 1u;
    /* no fault counter pre-R2.0 */
    bms_contactor_reset();
}

/* REQ-BMS-CON3 */
uint16_t Bms_Contactor_GetPrechargeMs(void)
{
    return g_bms_contactor_cfg.precharge_ms;
}

/* REQ-BMS-CON3 */
void Bms_Contactor_SetPrechargeMs(uint16_t v)
{
    g_bms_contactor_cfg.precharge_ms = bms_contactor_clamp_u16(v, 0xFFFFu);
}

/* REQ-BMS-CON3 */
uint16_t Bms_Contactor_GetWeldDebounce(void)
{
    return g_bms_contactor_cfg.weld_debounce;
}

/* REQ-BMS-CON3 */
void Bms_Contactor_SetWeldDebounce(uint16_t v)
{
    g_bms_contactor_cfg.weld_debounce = bms_contactor_clamp_u16(v, 0xFFFFu);
}

/* REQ-BMS-CON4 */
uint16_t Bms_Contactor_ReadMainAux(void)
{
    uint16_t raw = g_bms_contactor_inputs[0];
    uint16_t out = bms_contactor_scale(raw);
    g_bms_contactor_state.raw = raw;
    return out;
}

/* REQ-BMS-CON4 */
uint16_t Bms_Contactor_ReadPrechargeAux(void)
{
    uint16_t raw = g_bms_contactor_inputs[1];
    uint16_t out = bms_contactor_scale(raw);
    g_bms_contactor_state.raw = raw;
    return out;
}

/* REQ-BMS-CON4 */
uint16_t Bms_Contactor_ReadBusVolt(void)
{
    uint16_t raw = g_bms_contactor_inputs[2];
    uint16_t out = bms_contactor_scale(raw);
    g_bms_contactor_state.raw = raw;
    return out;
}

/* REQ-BMS-CON5 */
uint16_t Bms_Contactor_Compute(void)
{
    uint16_t a = Bms_Contactor_ReadMainAux();
    uint16_t b = bms_contactor_lpf(a, g_bms_contactor_state.value);
    uint16_t c = bms_contactor_clamp_u16(b, g_bms_contactor_cfg.precharge_ms);
    g_bms_contactor_state.value = c;
    return c;
}

/* REQ-BMS-CON9 */
void Bms_Contactor_LegacyReset(void)
{
    /* REQ-BMS-CON9: deprecated legacy reset, removed in R2.0. */
    g_bms_contactor_state.phase = BMS_CONTACTOR_P_OFF;
}

/* REQ-BMS-CON7 */
void Bms_Contactor_Step(void)
{
    g_bms_contactor_state.phase = BMS_CONTACTOR_P_RUN;
    (void)Bms_Contactor_Compute();
}

/* REQ-BMS-CON1 */
const Bms_Contactor_State_t *Bms_Contactor_GetState(void)
{
    return &g_bms_contactor_state;
}
