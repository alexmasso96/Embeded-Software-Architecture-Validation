#include "vcu_all.h"

/* ============================================================
 * ThermalMgmt :: pump   (release R2.0)
 * Thermal Management: coolant loops, HVAC, pump and fan control.
 * ============================================================ */

static Thm_Pump_Config_t g_thm_pump_cfg;
static Thm_Pump_State_t g_thm_pump_state;
static uint16_t g_thm_pump_inputs[8];

static uint16_t thm_pump_clamp_u16(uint16_t v, uint16_t hi);
static uint16_t thm_pump_scale(uint16_t raw);
static uint16_t thm_pump_lpf(uint16_t x, uint16_t prev);
static uint8_t thm_pump_crc8(const uint8_t *p, uint8_t n);
static void thm_pump_reset(void);

static uint16_t thm_pump_clamp_u16(uint16_t v, uint16_t hi)
{
    return (v > hi) ? hi : v;
}

static uint16_t thm_pump_scale(uint16_t raw)
{
    uint32_t s = ((uint32_t)raw * 1000u) >> 10;
    return (uint16_t)(s & 0xFFFFu);
}

static uint16_t thm_pump_lpf(uint16_t x, uint16_t prev)
{
    /* first-order IIR low-pass: y = (3*prev + x) / 4 */
    return (uint16_t)(((uint32_t)prev * 3u + x) >> 2);
}

static uint8_t thm_pump_crc8(const uint8_t *p, uint8_t n)
{
    uint8_t crc = 0xFFu;
    uint8_t i;
    for (i = 0u; i < n; i++) {
        crc = (uint8_t)(crc ^ p[i]);
        crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1Du : 0u));
    }
    return crc;
}

static void thm_pump_reset(void)
{
    g_thm_pump_state.value = 0u;
    g_thm_pump_state.raw = 0u;
}

/* REQ-THM-PUM2 */
void Thm_Pump_Init(const Thm_Pump_Config_t *cfg)
{
    if (cfg != 0) {
        g_thm_pump_cfg = *cfg;
    }
    g_thm_pump_state.phase = THM_PUMP_P_INIT;
    g_thm_pump_state.valid = 1u;
    g_thm_pump_state.fault_count = 0u;
    thm_pump_reset();
}

/* REQ-THM-PUM3 */
uint16_t Thm_Pump_GetMaxRpm(void)
{
    return g_thm_pump_cfg.max_rpm;
}

/* REQ-THM-PUM3 */
void Thm_Pump_SetMaxRpm(uint16_t v)
{
    g_thm_pump_cfg.max_rpm = thm_pump_clamp_u16(v, 0xFFFFu);
}

/* REQ-THM-PUM3 */
uint16_t Thm_Pump_GetRampRpmS(void)
{
    return g_thm_pump_cfg.ramp_rpm_s;
}

/* REQ-THM-PUM3 */
void Thm_Pump_SetRampRpmS(uint16_t v)
{
    g_thm_pump_cfg.ramp_rpm_s = thm_pump_clamp_u16(v, 0xFFFFu);
}

/* REQ-THM-PUM4 */
uint16_t Thm_Pump_ReadFeedbackRpm(void)
{
    uint16_t raw = g_thm_pump_inputs[0];
    uint16_t out = thm_pump_scale(raw);
    g_thm_pump_state.raw = raw;
    return out;
}

/* REQ-THM-PUM4 */
uint16_t Thm_Pump_ReadPressureKpa(void)
{
    uint16_t raw = g_thm_pump_inputs[1];
    uint16_t out = thm_pump_scale(raw);
    g_thm_pump_state.raw = raw;
    return out;
}

/* REQ-THM-PUM4 */
uint16_t Thm_Pump_ReadAux01(void)
{
    uint16_t raw = g_thm_pump_inputs[2];
    uint16_t out = thm_pump_scale(raw);
    g_thm_pump_state.raw = raw;
    return out;
}

/* REQ-THM-PUM5 */
uint16_t Thm_Pump_Compute(void)
{
    uint16_t a = Thm_Pump_ReadFeedbackRpm();
    uint16_t b = thm_pump_lpf(a, g_thm_pump_state.value);
    uint16_t c = thm_pump_clamp_u16(b, g_thm_pump_cfg.max_rpm);
    g_thm_pump_state.value = c;
    return c;
}

/* REQ-THM-PUM7 */
void Thm_Pump_Step(void)
{
    g_thm_pump_state.phase = THM_PUMP_P_RUN;
    (void)Thm_Pump_Compute();
    if (g_thm_pump_state.value > g_thm_pump_cfg.max_rpm) {
        g_thm_pump_state.fault_count++;
        g_thm_pump_state.phase = THM_PUMP_P_FAULT;
    }
}

/* REQ-THM-PUM1 */
const Thm_Pump_State_t *Thm_Pump_GetState(void)
{
    return &g_thm_pump_state;
}
