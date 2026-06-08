#include "wlc_main.h"
#include "wlc_motor.h"
#include "wlc_sensor.h"
#include "wlc_safety.h"

/* Module-private state. */
static WLC_State_t   g_wlc_state;                 /* REQ-WLC-011 */
static WLC_Config_t  g_wlc_cfg;

/* REQ-WLC-003: Anti-pinch shall trigger when current exceeds the configured
 * limit. v2: threshold now comes from calibration (current_limit_ma) with a
 * small hysteresis band instead of a hard-coded constant. */
static uint8_t WLC_DetectPinch(void)
{
    uint16_t cur = WLC_ReadCurrent();
    uint16_t trip = g_wlc_cfg.current_limit_ma;
    g_wlc_state.current_ma = cur;
    if (!g_wlc_cfg.pinch_enabled) {
        return 0u;
    }
    if (cur > trip) {
        return 1u;
    }
    /* hysteresis: clear latched flag only when well below the trip point */
    if (cur < (trip - 200u)) {
        g_wlc_state.pinch_flag = 0u;
    }
    return 0u;
}

static void WLC_UpdateStateMachine(void)
{
    g_wlc_state.position = WLC_ReadHallPosition();

    if (WLC_DetectPinch()) {
        g_wlc_state.phase      = (uint8_t)WLC_PINCH_STOP;
        g_wlc_state.pinch_flag = 1u;
        WLC_MotorStop();
        WLC_AutoReverse(&g_wlc_state);   /* REQ-WLC-050 */
    } else if (g_wlc_state.phase == (uint8_t)WLC_MOVING_UP) {
        WLC_MotorSetDuty(g_wlc_cfg.max_duty);
    }
}

void WLC_Init(const WLC_Config_t *cfg)
{
    g_wlc_cfg = *cfg;
    WLC_MotorInit(cfg);
    g_wlc_state.phase         = (uint8_t)WLC_IDLE;
    g_wlc_state.pinch_flag    = 0u;
    g_wlc_state.reverse_count = 0u;
}

/* REQ-WLC-040: The cyclic task shall execute the control loop. */
void WLC_Cyclic(void)
{
    WLC_UpdateStateMachine();
}

const WLC_State_t *WLC_GetState(void)
{
    return &g_wlc_state;
}
