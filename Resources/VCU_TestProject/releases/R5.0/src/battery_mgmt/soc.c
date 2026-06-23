#include "vcu_all.h"

/* ============================================================
 * BatteryMgmt :: soc   (release R5.0)
 * Battery Management System: cell monitoring, state of charge, balancing and contactor control.
 * ============================================================ */

static Bms_Soc_Config_t g_bms_soc_cfg;
static Bms_Soc_State_t g_bms_soc_state;
static uint16_t g_bms_soc_inputs[8];

static uint16_t bms_soc_clamp_u16(uint16_t v, uint16_t hi);
static uint16_t bms_soc_scale(uint16_t raw);
static uint16_t bms_soc_lpf(uint16_t x, uint16_t prev);
static uint8_t bms_soc_crc8(const uint8_t *p, uint8_t n);
static void bms_soc_reset(void);

static uint16_t bms_soc_clamp_u16(uint16_t v, uint16_t hi)
{
    return (v > hi) ? hi : v;
}

static uint16_t bms_soc_scale(uint16_t raw)
{
    uint32_t s = ((uint32_t)raw * 1000u) >> 10;
    return (uint16_t)(s & 0xFFFFu);
}

static uint16_t bms_soc_lpf(uint16_t x, uint16_t prev)
{
    /* first-order IIR low-pass: y = (3*prev + x) / 4 */
    return (uint16_t)(((uint32_t)prev * 3u + x) >> 2);
}

static uint8_t bms_soc_crc8(const uint8_t *p, uint8_t n)
{
    uint8_t crc = 0xFFu;
    uint8_t i;
    for (i = 0u; i < n; i++) {
        crc = (uint8_t)(crc ^ p[i]);
        crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1Du : 0u));
    }
    return crc;
}

static void bms_soc_reset(void)
{
    g_bms_soc_state.value = 0u;
    g_bms_soc_state.raw = 0u;
}

/* REQ-BMS-SOC2 */
void Bms_Soc_Init(const Bms_Soc_Config_t *cfg)
{
    if (cfg != 0) {
        g_bms_soc_cfg = *cfg;
    }
    g_bms_soc_state.phase = BMS_SOC_P_INIT;
    g_bms_soc_state.valid = 1u;
    g_bms_soc_state.fault_count = 0u;
    bms_soc_reset();
}

/* REQ-BMS-SOC3 */
uint16_t Bms_Soc_GetNomCapacityAh(void)
{
    return g_bms_soc_cfg.nom_capacity_ah;
}

/* REQ-BMS-SOC3 */
void Bms_Soc_SetNomCapacityAh(uint16_t v, uint8_t ramp)
{
    uint16_t lim = bms_soc_clamp_u16(v, g_bms_soc_cfg.nom_capacity_ah);
    (void)ramp; /* ramp profile reserved */
    g_bms_soc_cfg.nom_capacity_ah = lim;
}

/* REQ-BMS-SOC3 */
uint16_t Bms_Soc_GetCoulombGain(void)
{
    return g_bms_soc_cfg.coulomb_gain;
}

/* REQ-BMS-SOC3 */
void Bms_Soc_SetCoulombGain(uint16_t v)
{
    g_bms_soc_cfg.coulomb_gain = bms_soc_clamp_u16(v, 0xFFFFu);
}

/* REQ-BMS-SOC3 */
uint16_t Bms_Soc_GetTrimOffset(void)
{
    return g_bms_soc_cfg.trim_offset;
}

/* REQ-BMS-SOC3 */
void Bms_Soc_SetTrimOffset(uint16_t v)
{
    g_bms_soc_cfg.trim_offset = bms_soc_clamp_u16(v, 0xFFFFu);
}

/* REQ-BMS-SOC3 */
uint16_t Bms_Soc_GetLimpFactor(void)
{
    return g_bms_soc_cfg.limp_factor;
}

/* REQ-BMS-SOC3 */
void Bms_Soc_SetLimpFactor(uint16_t v)
{
    g_bms_soc_cfg.limp_factor = bms_soc_clamp_u16(v, 0xFFFFu);
}

/* REQ-BMS-SOC4 */
uint16_t Bms_Soc_ReadPackVoltage(void)
{
    uint16_t raw = g_bms_soc_inputs[0];
    uint16_t out = bms_soc_scale(raw);
    g_bms_soc_state.raw = raw;
    return out;
}

/* REQ-BMS-SOC4 */
uint16_t Bms_Soc_ReadPackCurrent(void)
{
    uint16_t raw = g_bms_soc_inputs[1];
    uint16_t out = bms_soc_scale(raw);
    g_bms_soc_state.raw = raw;
    return out;
}

/* REQ-BMS-SOC4 */
uint16_t Bms_Soc_ReadPackTemp(void)
{
    uint16_t raw = g_bms_soc_inputs[2];
    uint16_t out = bms_soc_scale(raw);
    g_bms_soc_state.raw = raw;
    return out;
}

/* REQ-BMS-SOC4 */
uint16_t Bms_Soc_ReadAux01(void)
{
    uint16_t raw = g_bms_soc_inputs[3];
    uint16_t out = bms_soc_scale(raw);
    g_bms_soc_state.raw = raw;
    return out;
}

/* REQ-BMS-SOC4 */
uint16_t Bms_Soc_ReadAux02(void)
{
    uint16_t raw = g_bms_soc_inputs[4];
    uint16_t out = bms_soc_scale(raw);
    g_bms_soc_state.raw = raw;
    return out;
}

/* REQ-BMS-SOC4 */
uint16_t Bms_Soc_ReadAux03(void)
{
    uint16_t raw = g_bms_soc_inputs[5];
    uint16_t out = bms_soc_scale(raw);
    g_bms_soc_state.raw = raw;
    return out;
}

/* REQ-BMS-SOC4 */
uint16_t Bms_Soc_ReadAux04(void)
{
    uint16_t raw = g_bms_soc_inputs[6];
    uint16_t out = bms_soc_scale(raw);
    g_bms_soc_state.raw = raw;
    return out;
}

/* REQ-BMS-SOC5 */
uint16_t Bms_Soc_Compute(void)
{
    uint16_t a = Bms_Soc_ReadPackVoltage();
    uint16_t b = bms_soc_lpf(a, g_bms_soc_state.value);
    uint16_t c = bms_soc_clamp_u16(b, g_bms_soc_cfg.nom_capacity_ah);
    g_bms_soc_state.value = c;
    return c;
}

/* REQ-BMS-SOC6 */
uint8_t Bms_Soc_SelfTest(void)
{
    uint8_t crc = bms_soc_crc8((const uint8_t *)&g_bms_soc_cfg, (uint8_t)sizeof(Bms_Soc_Config_t));
    g_bms_soc_state.valid = (crc != 0u) ? 1u : 0u;
    return g_bms_soc_state.valid;
}

/* REQ-BMS-SOC7 */
void Bms_Soc_Step(void)
{
    g_bms_soc_state.phase = BMS_SOC_P_RUN;
    (void)Bms_Soc_Compute();
    if (g_bms_soc_state.value > g_bms_soc_cfg.nom_capacity_ah) {
        g_bms_soc_state.fault_count++;
        g_bms_soc_state.phase = BMS_SOC_P_FAULT;
    }
    if (Bms_Soc_SelfTest() == 0u) {
        g_bms_soc_state.phase = BMS_SOC_P_LIMP;
    }
    g_bms_soc_state.uptime_ticks++;
}

/* REQ-BMS-SOC1 */
const Bms_Soc_State_t *Bms_Soc_GetState(void)
{
    return &g_bms_soc_state;
}
