#include "vcu_all.h"

/* ============================================================
 * ThermalMgmt :: fan   (release R4.0)
 * Thermal Management: coolant loops, HVAC, pump and fan control.
 * ============================================================ */

static Thm_Fan_Config_t g_thm_fan_cfg;
static Thm_Fan_State_t g_thm_fan_state;
static uint16_t g_thm_fan_inputs[8];

static uint16_t thm_fan_clamp_u16(uint16_t v, uint16_t hi);
static uint16_t thm_fan_scale(uint16_t raw);
static uint16_t thm_fan_lpf(uint16_t x, uint16_t prev);
static uint8_t thm_fan_crc8(const uint8_t *p, uint8_t n);
static void thm_fan_reset(void);

static uint16_t thm_fan_clamp_u16(uint16_t v, uint16_t hi)
{
    return (v > hi) ? hi : v;
}

static uint16_t thm_fan_scale(uint16_t raw)
{
    uint32_t s = ((uint32_t)raw * 1000u) >> 10;
    return (uint16_t)(s & 0xFFFFu);
}

static uint16_t thm_fan_lpf(uint16_t x, uint16_t prev)
{
    /* first-order IIR low-pass: y = (3*prev + x) / 4 */
    return (uint16_t)(((uint32_t)prev * 3u + x) >> 2);
}

static uint8_t thm_fan_crc8(const uint8_t *p, uint8_t n)
{
    uint8_t crc = 0xFFu;
    uint8_t i;
    for (i = 0u; i < n; i++) {
        crc = (uint8_t)(crc ^ p[i]);
        crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1Du : 0u));
    }
    return crc;
}

static void thm_fan_reset(void)
{
    g_thm_fan_state.value = 0u;
    g_thm_fan_state.raw = 0u;
}

/* REQ-THM-FAN2 */
void Thm_Fan_Init(const Thm_Fan_Config_t *cfg)
{
    if (cfg != 0) {
        g_thm_fan_cfg = *cfg;
    }
    g_thm_fan_state.phase = THM_FAN_P_INIT;
    g_thm_fan_state.valid = 1u;
    g_thm_fan_state.fault_count = 0u;
    thm_fan_reset();
}

/* REQ-THM-FAN3 */
uint16_t Thm_Fan_GetOnThreshC(void)
{
    return g_thm_fan_cfg.on_thresh_c;
}

/* REQ-THM-FAN3 */
void Thm_Fan_SetOnThreshC(uint16_t v, uint8_t ramp)
{
    uint16_t lim = thm_fan_clamp_u16(v, g_thm_fan_cfg.on_thresh_c);
    (void)ramp; /* ramp profile reserved */
    g_thm_fan_cfg.on_thresh_c = lim;
}

/* REQ-THM-FAN3 */
uint16_t Thm_Fan_GetOffThreshC(void)
{
    return g_thm_fan_cfg.off_thresh_c;
}

/* REQ-THM-FAN3 */
void Thm_Fan_SetOffThreshC(uint16_t v)
{
    g_thm_fan_cfg.off_thresh_c = thm_fan_clamp_u16(v, 0xFFFFu);
}

/* REQ-THM-FAN3 */
uint16_t Thm_Fan_GetTrimOffset(void)
{
    return g_thm_fan_cfg.trim_offset;
}

/* REQ-THM-FAN3 */
void Thm_Fan_SetTrimOffset(uint16_t v)
{
    g_thm_fan_cfg.trim_offset = thm_fan_clamp_u16(v, 0xFFFFu);
}

/* REQ-THM-FAN4 */
uint16_t Thm_Fan_ReadRadiatorC(void)
{
    uint16_t raw = g_thm_fan_inputs[0];
    uint16_t out = thm_fan_scale(raw);
    g_thm_fan_state.raw = raw;
    return out;
}

/* REQ-THM-FAN4 */
uint16_t Thm_Fan_ReadFanRpm(void)
{
    uint16_t raw = g_thm_fan_inputs[1];
    uint16_t out = thm_fan_scale(raw);
    g_thm_fan_state.raw = raw;
    return out;
}

/* REQ-THM-FAN4 */
uint16_t Thm_Fan_ReadAux01(void)
{
    uint16_t raw = g_thm_fan_inputs[2];
    uint16_t out = thm_fan_scale(raw);
    g_thm_fan_state.raw = raw;
    return out;
}

/* REQ-THM-FAN4 */
uint16_t Thm_Fan_ReadAux02(void)
{
    uint16_t raw = g_thm_fan_inputs[3];
    uint16_t out = thm_fan_scale(raw);
    g_thm_fan_state.raw = raw;
    return out;
}

/* REQ-THM-FAN4 */
uint16_t Thm_Fan_ReadAux03(void)
{
    uint16_t raw = g_thm_fan_inputs[4];
    uint16_t out = thm_fan_scale(raw);
    g_thm_fan_state.raw = raw;
    return out;
}

/* REQ-THM-FAN5 */
uint16_t Thm_Fan_Compute(void)
{
    uint16_t a = Thm_Fan_ReadRadiatorC();
    uint16_t b = thm_fan_lpf(a, g_thm_fan_state.value);
    uint16_t c = thm_fan_clamp_u16(b, g_thm_fan_cfg.on_thresh_c);
    g_thm_fan_state.value = c;
    return c;
}

/* REQ-THM-FAN6 */
uint8_t Thm_Fan_SelfTest(void)
{
    uint8_t crc = thm_fan_crc8((const uint8_t *)&g_thm_fan_cfg, (uint8_t)sizeof(Thm_Fan_Config_t));
    g_thm_fan_state.valid = (crc != 0u) ? 1u : 0u;
    return g_thm_fan_state.valid;
}

/* REQ-THM-FAN7 */
void Thm_Fan_Step(void)
{
    g_thm_fan_state.phase = THM_FAN_P_RUN;
    (void)Thm_Fan_Compute();
    if (g_thm_fan_state.value > g_thm_fan_cfg.on_thresh_c) {
        g_thm_fan_state.fault_count++;
        g_thm_fan_state.phase = THM_FAN_P_FAULT;
    }
    if (Thm_Fan_SelfTest() == 0u) {
        g_thm_fan_state.phase = THM_FAN_P_LIMP;
    }
    g_thm_fan_state.uptime_ticks++;
}

/* REQ-THM-FAN1 */
const Thm_Fan_State_t *Thm_Fan_GetState(void)
{
    return &g_thm_fan_state;
}
