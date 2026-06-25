#include "vcu_all.h"

/* ============================================================
 * CommGateway :: canrouter   (release R1.0)
 * Communication Gateway: CAN/LIN routing, signal mapping and bus monitoring.
 * ============================================================ */

static Com_Canrouter_Config_t g_com_canrouter_cfg;
static Com_Canrouter_State_t g_com_canrouter_state;
static uint16_t g_com_canrouter_inputs[8];

static uint16_t com_canrouter_clamp_u16(uint16_t v, uint16_t hi);
static uint16_t com_canrouter_scale(uint16_t raw);
static uint16_t com_canrouter_lpf(uint16_t x, uint16_t prev);
static uint8_t com_canrouter_crc8(const uint8_t *p, uint8_t n);
static void com_canrouter_reset(void);

static uint16_t com_canrouter_clamp_u16(uint16_t v, uint16_t hi)
{
    return (v > hi) ? hi : v;
}

static uint16_t com_canrouter_scale(uint16_t raw)
{
    uint32_t s = ((uint32_t)raw * 1000u) >> 10;
    return (uint16_t)(s & 0xFFFFu);
}

static uint16_t com_canrouter_lpf(uint16_t x, uint16_t prev)
{
    /* first-order IIR low-pass: y = (3*prev + x) / 4 */
    return (uint16_t)(((uint32_t)prev * 3u + x) >> 2);
}

static uint8_t com_canrouter_crc8(const uint8_t *p, uint8_t n)
{
    uint8_t crc = 0xFFu;
    uint8_t i;
    for (i = 0u; i < n; i++) {
        crc = (uint8_t)(crc ^ p[i]);
        crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1Du : 0u));
    }
    return crc;
}

static void com_canrouter_reset(void)
{
    g_com_canrouter_state.value = 0u;
    g_com_canrouter_state.raw = 0u;
}

/* REQ-COM-CAN2 */
void Com_Canrouter_Init(const Com_Canrouter_Config_t *cfg)
{
    if (cfg != 0) {
        g_com_canrouter_cfg = *cfg;
    }
    g_com_canrouter_state.phase = COM_CANROUTER_P_INIT;
    g_com_canrouter_state.valid = 1u;
    /* no fault counter pre-R2.0 */
    com_canrouter_reset();
}

/* REQ-COM-CAN3 */
uint16_t Com_Canrouter_GetBusLoadLimit(void)
{
    return g_com_canrouter_cfg.bus_load_limit;
}

/* REQ-COM-CAN3 */
void Com_Canrouter_SetBusLoadLimit(uint16_t v)
{
    g_com_canrouter_cfg.bus_load_limit = com_canrouter_clamp_u16(v, 0xFFFFu);
}

/* REQ-COM-CAN3 */
uint16_t Com_Canrouter_GetRouteTableLen(void)
{
    return g_com_canrouter_cfg.route_table_len;
}

/* REQ-COM-CAN3 */
void Com_Canrouter_SetRouteTableLen(uint16_t v)
{
    g_com_canrouter_cfg.route_table_len = com_canrouter_clamp_u16(v, 0xFFFFu);
}

/* REQ-COM-CAN4 */
uint16_t Com_Canrouter_ReadRxId(void)
{
    uint16_t raw = g_com_canrouter_inputs[0];
    uint16_t out = com_canrouter_scale(raw);
    g_com_canrouter_state.raw = raw;
    return out;
}

/* REQ-COM-CAN4 */
uint16_t Com_Canrouter_ReadRxDlc(void)
{
    uint16_t raw = g_com_canrouter_inputs[1];
    uint16_t out = com_canrouter_scale(raw);
    g_com_canrouter_state.raw = raw;
    return out;
}

/* REQ-COM-CAN4 */
uint16_t Com_Canrouter_ReadBusOff(void)
{
    uint16_t raw = g_com_canrouter_inputs[2];
    uint16_t out = com_canrouter_scale(raw);
    g_com_canrouter_state.raw = raw;
    return out;
}

/* REQ-COM-CAN5 */
uint16_t Com_Canrouter_Compute(void)
{
    uint16_t a = Com_Canrouter_ReadRxId();
    uint16_t b = com_canrouter_lpf(a, g_com_canrouter_state.value);
    uint16_t c = com_canrouter_clamp_u16(b, g_com_canrouter_cfg.bus_load_limit);
    g_com_canrouter_state.value = c;
    return c;
}

/* REQ-COM-CAN9 */
void Com_Canrouter_LegacyReset(void)
{
    /* REQ-COM-CAN9: deprecated legacy reset, removed in R2.0. */
    g_com_canrouter_state.phase = COM_CANROUTER_P_OFF;
}

/* REQ-COM-CAN7 */
void Com_Canrouter_Step(void)
{
    g_com_canrouter_state.phase = COM_CANROUTER_P_RUN;
    (void)Com_Canrouter_Compute();
}

/* REQ-COM-CAN1 */
const Com_Canrouter_State_t *Com_Canrouter_GetState(void)
{
    return &g_com_canrouter_state;
}
