#include "vcu_all.h"

/* ============================================================
 * ChargingCtrl :: pilot   (release R3.0)
 * Charging Control (introduced R3.0): AC/DC charging state machine, control pilot and metering.
 * ============================================================ */

static Chg_Pilot_Config_t g_chg_pilot_cfg;
static Chg_Pilot_State_t g_chg_pilot_state;
static uint16_t g_chg_pilot_inputs[8];

static uint16_t chg_pilot_clamp_u16(uint16_t v, uint16_t hi);
static uint16_t chg_pilot_scale(uint16_t raw);
static uint16_t chg_pilot_lpf(uint16_t x, uint16_t prev);
static uint8_t chg_pilot_crc8(const uint8_t *p, uint8_t n);
static void chg_pilot_reset(void);

static uint16_t chg_pilot_clamp_u16(uint16_t v, uint16_t hi)
{
    return (v > hi) ? hi : v;
}

static uint16_t chg_pilot_scale(uint16_t raw)
{
    uint32_t s = ((uint32_t)raw * 1000u) >> 10;
    return (uint16_t)(s & 0xFFFFu);
}

static uint16_t chg_pilot_lpf(uint16_t x, uint16_t prev)
{
    /* first-order IIR low-pass: y = (3*prev + x) / 4 */
    return (uint16_t)(((uint32_t)prev * 3u + x) >> 2);
}

static uint8_t chg_pilot_crc8(const uint8_t *p, uint8_t n)
{
    uint8_t crc = 0xFFu;
    uint8_t i;
    for (i = 0u; i < n; i++) {
        crc = (uint8_t)(crc ^ p[i]);
        crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1Du : 0u));
    }
    return crc;
}

static void chg_pilot_reset(void)
{
    g_chg_pilot_state.value = 0u;
    g_chg_pilot_state.raw = 0u;
}

/* REQ-CHG-PIL2 */
void Chg_Pilot_Init(const Chg_Pilot_Config_t *cfg)
{
    if (cfg != 0) {
        g_chg_pilot_cfg = *cfg;
    }
    g_chg_pilot_state.phase = CHG_PILOT_P_INIT;
    g_chg_pilot_state.valid = 1u;
    g_chg_pilot_state.fault_count = 0u;
    chg_pilot_reset();
}

/* REQ-CHG-PIL3 */
uint16_t Chg_Pilot_GetDutyToAmps(void)
{
    return g_chg_pilot_cfg.duty_to_amps;
}

/* REQ-CHG-PIL3 */
void Chg_Pilot_SetDutyToAmps(uint16_t v)
{
    g_chg_pilot_cfg.duty_to_amps = chg_pilot_clamp_u16(v, 0xFFFFu);
}

/* REQ-CHG-PIL3 */
uint16_t Chg_Pilot_GetProxResistor(void)
{
    return g_chg_pilot_cfg.prox_resistor;
}

/* REQ-CHG-PIL3 */
void Chg_Pilot_SetProxResistor(uint16_t v)
{
    g_chg_pilot_cfg.prox_resistor = chg_pilot_clamp_u16(v, 0xFFFFu);
}

/* REQ-CHG-PIL3 */
uint16_t Chg_Pilot_GetTrimOffset(void)
{
    return g_chg_pilot_cfg.trim_offset;
}

/* REQ-CHG-PIL3 */
void Chg_Pilot_SetTrimOffset(uint16_t v)
{
    g_chg_pilot_cfg.trim_offset = chg_pilot_clamp_u16(v, 0xFFFFu);
}

/* REQ-CHG-PIL4 */
uint16_t Chg_Pilot_ReadCpVolt(void)
{
    uint16_t raw = g_chg_pilot_inputs[0];
    uint16_t out = chg_pilot_scale(raw);
    g_chg_pilot_state.raw = raw;
    return out;
}

/* REQ-CHG-PIL4 */
uint16_t Chg_Pilot_ReadPpVolt(void)
{
    uint16_t raw = g_chg_pilot_inputs[1];
    uint16_t out = chg_pilot_scale(raw);
    g_chg_pilot_state.raw = raw;
    return out;
}

/* REQ-CHG-PIL4 */
uint16_t Chg_Pilot_ReadAux01(void)
{
    uint16_t raw = g_chg_pilot_inputs[2];
    uint16_t out = chg_pilot_scale(raw);
    g_chg_pilot_state.raw = raw;
    return out;
}

/* REQ-CHG-PIL4 */
uint16_t Chg_Pilot_ReadAux02(void)
{
    uint16_t raw = g_chg_pilot_inputs[3];
    uint16_t out = chg_pilot_scale(raw);
    g_chg_pilot_state.raw = raw;
    return out;
}

/* REQ-CHG-PIL5 */
uint16_t Chg_Pilot_Compute(void)
{
    uint16_t a = Chg_Pilot_ReadCpVolt();
    uint16_t b = chg_pilot_lpf(a, g_chg_pilot_state.value);
    uint16_t c = chg_pilot_clamp_u16(b, g_chg_pilot_cfg.duty_to_amps);
    g_chg_pilot_state.value = c;
    return c;
}

/* REQ-CHG-PIL6 */
uint8_t Chg_Pilot_SelfTest(void)
{
    uint8_t crc = chg_pilot_crc8((const uint8_t *)&g_chg_pilot_cfg, (uint8_t)sizeof(Chg_Pilot_Config_t));
    g_chg_pilot_state.valid = (crc != 0u) ? 1u : 0u;
    return g_chg_pilot_state.valid;
}

/* REQ-CHG-PIL7 */
void Chg_Pilot_Step(void)
{
    g_chg_pilot_state.phase = CHG_PILOT_P_RUN;
    (void)Chg_Pilot_Compute();
    if (g_chg_pilot_state.value > g_chg_pilot_cfg.duty_to_amps) {
        g_chg_pilot_state.fault_count++;
        g_chg_pilot_state.phase = CHG_PILOT_P_FAULT;
    }
    if (Chg_Pilot_SelfTest() == 0u) {
        g_chg_pilot_state.phase = CHG_PILOT_P_LIMP;
    }
}

/* REQ-CHG-PIL1 */
const Chg_Pilot_State_t *Chg_Pilot_GetState(void)
{
    return &g_chg_pilot_state;
}
