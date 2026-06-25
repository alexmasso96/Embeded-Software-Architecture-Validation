#include "vcu_all.h"

/* ============================================================
 * ChargingCtrl :: metering   (release R5.0)
 * Charging Control (introduced R3.0): AC/DC charging state machine, control pilot and metering.
 * ============================================================ */

static Chg_Metering_Config_t g_chg_metering_cfg;
static Chg_Metering_State_t g_chg_metering_state;
static uint16_t g_chg_metering_inputs[8];

static uint16_t chg_metering_clamp_u16(uint16_t v, uint16_t hi);
static uint16_t chg_metering_scale(uint16_t raw);
static uint16_t chg_metering_lpf(uint16_t x, uint16_t prev);
static uint8_t chg_metering_crc8(const uint8_t *p, uint8_t n);
static void chg_metering_reset(void);

static uint16_t chg_metering_clamp_u16(uint16_t v, uint16_t hi)
{
    return (v > hi) ? hi : v;
}

static uint16_t chg_metering_scale(uint16_t raw)
{
    uint32_t s = ((uint32_t)raw * 1000u) >> 10;
    return (uint16_t)(s & 0xFFFFu);
}

static uint16_t chg_metering_lpf(uint16_t x, uint16_t prev)
{
    /* first-order IIR low-pass: y = (3*prev + x) / 4 */
    return (uint16_t)(((uint32_t)prev * 3u + x) >> 2);
}

static uint8_t chg_metering_crc8(const uint8_t *p, uint8_t n)
{
    uint8_t crc = 0xFFu;
    uint8_t i;
    for (i = 0u; i < n; i++) {
        crc = (uint8_t)(crc ^ p[i]);
        crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1Du : 0u));
    }
    return crc;
}

static void chg_metering_reset(void)
{
    g_chg_metering_state.value = 0u;
    g_chg_metering_state.raw = 0u;
}

/* REQ-CHG-MET2 */
void Chg_Metering_Init(const Chg_Metering_Config_t *cfg)
{
    if (cfg != 0) {
        g_chg_metering_cfg = *cfg;
    }
    g_chg_metering_state.phase = CHG_METERING_P_INIT;
    g_chg_metering_state.valid = 1u;
    g_chg_metering_state.fault_count = 0u;
    chg_metering_reset();
}

/* REQ-CHG-MET3 */
uint16_t Chg_Metering_GetEnergyScale(void)
{
    return g_chg_metering_cfg.energy_scale;
}

/* REQ-CHG-MET3 */
void Chg_Metering_SetEnergyScale(uint16_t v, uint8_t ramp)
{
    uint16_t lim = chg_metering_clamp_u16(v, g_chg_metering_cfg.energy_scale);
    (void)ramp; /* ramp profile reserved */
    g_chg_metering_cfg.energy_scale = lim;
}

/* REQ-CHG-MET3 */
uint16_t Chg_Metering_GetTariffId(void)
{
    return g_chg_metering_cfg.tariff_id;
}

/* REQ-CHG-MET3 */
void Chg_Metering_SetTariffId(uint16_t v)
{
    g_chg_metering_cfg.tariff_id = chg_metering_clamp_u16(v, 0xFFFFu);
}

/* REQ-CHG-MET3 */
uint16_t Chg_Metering_GetTrimOffset(void)
{
    return g_chg_metering_cfg.trim_offset;
}

/* REQ-CHG-MET3 */
void Chg_Metering_SetTrimOffset(uint16_t v)
{
    g_chg_metering_cfg.trim_offset = chg_metering_clamp_u16(v, 0xFFFFu);
}

/* REQ-CHG-MET3 */
uint16_t Chg_Metering_GetLimpFactor(void)
{
    return g_chg_metering_cfg.limp_factor;
}

/* REQ-CHG-MET3 */
void Chg_Metering_SetLimpFactor(uint16_t v)
{
    g_chg_metering_cfg.limp_factor = chg_metering_clamp_u16(v, 0xFFFFu);
}

/* REQ-CHG-MET4 */
uint16_t Chg_Metering_ReadDcCurrent(void)
{
    uint16_t raw = g_chg_metering_inputs[0];
    uint16_t out = chg_metering_scale(raw);
    g_chg_metering_state.raw = raw;
    return out;
}

/* REQ-CHG-MET4 */
uint16_t Chg_Metering_ReadDcVolt(void)
{
    uint16_t raw = g_chg_metering_inputs[1];
    uint16_t out = chg_metering_scale(raw);
    g_chg_metering_state.raw = raw;
    return out;
}

/* REQ-CHG-MET4 */
uint16_t Chg_Metering_ReadAux01(void)
{
    uint16_t raw = g_chg_metering_inputs[2];
    uint16_t out = chg_metering_scale(raw);
    g_chg_metering_state.raw = raw;
    return out;
}

/* REQ-CHG-MET4 */
uint16_t Chg_Metering_ReadAux02(void)
{
    uint16_t raw = g_chg_metering_inputs[3];
    uint16_t out = chg_metering_scale(raw);
    g_chg_metering_state.raw = raw;
    return out;
}

/* REQ-CHG-MET4 */
uint16_t Chg_Metering_ReadAux03(void)
{
    uint16_t raw = g_chg_metering_inputs[4];
    uint16_t out = chg_metering_scale(raw);
    g_chg_metering_state.raw = raw;
    return out;
}

/* REQ-CHG-MET4 */
uint16_t Chg_Metering_ReadAux04(void)
{
    uint16_t raw = g_chg_metering_inputs[5];
    uint16_t out = chg_metering_scale(raw);
    g_chg_metering_state.raw = raw;
    return out;
}

/* REQ-CHG-MET5 */
uint16_t Chg_Metering_Compute(void)
{
    uint16_t a = Chg_Metering_ReadDcCurrent();
    uint16_t b = chg_metering_lpf(a, g_chg_metering_state.value);
    uint16_t c = chg_metering_clamp_u16(b, g_chg_metering_cfg.energy_scale);
    g_chg_metering_state.value = c;
    return c;
}

/* REQ-CHG-MET6 */
uint8_t Chg_Metering_SelfTest(void)
{
    uint8_t crc = chg_metering_crc8((const uint8_t *)&g_chg_metering_cfg, (uint8_t)sizeof(Chg_Metering_Config_t));
    g_chg_metering_state.valid = (crc != 0u) ? 1u : 0u;
    return g_chg_metering_state.valid;
}

/* REQ-CHG-MET7 */
void Chg_Metering_Step(void)
{
    g_chg_metering_state.phase = CHG_METERING_P_RUN;
    (void)Chg_Metering_Compute();
    if (g_chg_metering_state.value > g_chg_metering_cfg.energy_scale) {
        g_chg_metering_state.fault_count++;
        g_chg_metering_state.phase = CHG_METERING_P_FAULT;
    }
    if (Chg_Metering_SelfTest() == 0u) {
        g_chg_metering_state.phase = CHG_METERING_P_LIMP;
    }
    g_chg_metering_state.uptime_ticks++;
}

/* REQ-CHG-MET1 */
const Chg_Metering_State_t *Chg_Metering_GetState(void)
{
    return &g_chg_metering_state;
}
