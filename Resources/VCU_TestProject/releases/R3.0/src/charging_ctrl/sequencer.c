#include "vcu_all.h"

/* ============================================================
 * ChargingCtrl :: sequencer   (release R3.0)
 * Charging Control (introduced R3.0): AC/DC charging state machine, control pilot and metering.
 * ============================================================ */

static Chg_Sequencer_Config_t g_chg_sequencer_cfg;
static Chg_Sequencer_State_t g_chg_sequencer_state;
static uint16_t g_chg_sequencer_inputs[8];

static uint16_t chg_sequencer_clamp_u16(uint16_t v, uint16_t hi);
static uint16_t chg_sequencer_scale(uint16_t raw);
static uint16_t chg_sequencer_lpf(uint16_t x, uint16_t prev);
static uint8_t chg_sequencer_crc8(const uint8_t *p, uint8_t n);
static void chg_sequencer_reset(void);

static uint16_t chg_sequencer_clamp_u16(uint16_t v, uint16_t hi)
{
    return (v > hi) ? hi : v;
}

static uint16_t chg_sequencer_scale(uint16_t raw)
{
    uint32_t s = ((uint32_t)raw * 1000u) >> 10;
    return (uint16_t)(s & 0xFFFFu);
}

static uint16_t chg_sequencer_lpf(uint16_t x, uint16_t prev)
{
    /* first-order IIR low-pass: y = (3*prev + x) / 4 */
    return (uint16_t)(((uint32_t)prev * 3u + x) >> 2);
}

static uint8_t chg_sequencer_crc8(const uint8_t *p, uint8_t n)
{
    uint8_t crc = 0xFFu;
    uint8_t i;
    for (i = 0u; i < n; i++) {
        crc = (uint8_t)(crc ^ p[i]);
        crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1Du : 0u));
    }
    return crc;
}

static void chg_sequencer_reset(void)
{
    g_chg_sequencer_state.value = 0u;
    g_chg_sequencer_state.raw = 0u;
}

/* REQ-CHG-SEQ2 */
void Chg_Sequencer_Init(const Chg_Sequencer_Config_t *cfg)
{
    if (cfg != 0) {
        g_chg_sequencer_cfg = *cfg;
    }
    g_chg_sequencer_state.phase = CHG_SEQUENCER_P_INIT;
    g_chg_sequencer_state.valid = 1u;
    g_chg_sequencer_state.fault_count = 0u;
    chg_sequencer_reset();
}

/* REQ-CHG-SEQ3 */
uint16_t Chg_Sequencer_GetStateTimeoutMs(void)
{
    return g_chg_sequencer_cfg.state_timeout_ms;
}

/* REQ-CHG-SEQ3 */
void Chg_Sequencer_SetStateTimeoutMs(uint16_t v)
{
    g_chg_sequencer_cfg.state_timeout_ms = chg_sequencer_clamp_u16(v, 0xFFFFu);
}

/* REQ-CHG-SEQ3 */
uint16_t Chg_Sequencer_GetRetryLimit(void)
{
    return g_chg_sequencer_cfg.retry_limit;
}

/* REQ-CHG-SEQ3 */
void Chg_Sequencer_SetRetryLimit(uint16_t v)
{
    g_chg_sequencer_cfg.retry_limit = chg_sequencer_clamp_u16(v, 0xFFFFu);
}

/* REQ-CHG-SEQ3 */
uint16_t Chg_Sequencer_GetTrimOffset(void)
{
    return g_chg_sequencer_cfg.trim_offset;
}

/* REQ-CHG-SEQ3 */
void Chg_Sequencer_SetTrimOffset(uint16_t v)
{
    g_chg_sequencer_cfg.trim_offset = chg_sequencer_clamp_u16(v, 0xFFFFu);
}

/* REQ-CHG-SEQ4 */
uint16_t Chg_Sequencer_ReadContactorAux(void)
{
    uint16_t raw = g_chg_sequencer_inputs[0];
    uint16_t out = chg_sequencer_scale(raw);
    g_chg_sequencer_state.raw = raw;
    return out;
}

/* REQ-CHG-SEQ4 */
uint16_t Chg_Sequencer_ReadInsulationMohm(void)
{
    uint16_t raw = g_chg_sequencer_inputs[1];
    uint16_t out = chg_sequencer_scale(raw);
    g_chg_sequencer_state.raw = raw;
    return out;
}

/* REQ-CHG-SEQ4 */
uint16_t Chg_Sequencer_ReadAux01(void)
{
    uint16_t raw = g_chg_sequencer_inputs[2];
    uint16_t out = chg_sequencer_scale(raw);
    g_chg_sequencer_state.raw = raw;
    return out;
}

/* REQ-CHG-SEQ4 */
uint16_t Chg_Sequencer_ReadAux02(void)
{
    uint16_t raw = g_chg_sequencer_inputs[3];
    uint16_t out = chg_sequencer_scale(raw);
    g_chg_sequencer_state.raw = raw;
    return out;
}

/* REQ-CHG-SEQ5 */
uint16_t Chg_Sequencer_Compute(void)
{
    uint16_t a = Chg_Sequencer_ReadContactorAux();
    uint16_t b = chg_sequencer_lpf(a, g_chg_sequencer_state.value);
    uint16_t c = chg_sequencer_clamp_u16(b, g_chg_sequencer_cfg.state_timeout_ms);
    g_chg_sequencer_state.value = c;
    return c;
}

/* REQ-CHG-SEQ6 */
uint8_t Chg_Sequencer_SelfTest(void)
{
    uint8_t crc = chg_sequencer_crc8((const uint8_t *)&g_chg_sequencer_cfg, (uint8_t)sizeof(Chg_Sequencer_Config_t));
    g_chg_sequencer_state.valid = (crc != 0u) ? 1u : 0u;
    return g_chg_sequencer_state.valid;
}

/* REQ-CHG-SEQ7 */
void Chg_Sequencer_Step(void)
{
    g_chg_sequencer_state.phase = CHG_SEQUENCER_P_RUN;
    (void)Chg_Sequencer_Compute();
    if (g_chg_sequencer_state.value > g_chg_sequencer_cfg.state_timeout_ms) {
        g_chg_sequencer_state.fault_count++;
        g_chg_sequencer_state.phase = CHG_SEQUENCER_P_FAULT;
    }
    if (Chg_Sequencer_SelfTest() == 0u) {
        g_chg_sequencer_state.phase = CHG_SEQUENCER_P_LIMP;
    }
}

/* REQ-CHG-SEQ1 */
const Chg_Sequencer_State_t *Chg_Sequencer_GetState(void)
{
    return &g_chg_sequencer_state;
}
