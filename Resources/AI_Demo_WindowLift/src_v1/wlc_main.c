#include "wlc_main.h"
#include "wlc_motor.h"
#include "wlc_sensor.h"

/* Module-private state. */
static WLC_State_t   g_wlc_state;                 /* REQ-WLC-011 */
static WLC_Config_t  g_wlc_cfg;
static const uint16_t g_pinch_threshold_ma = 5000u; /* REQ-WLC-003 */

/* REQ-WLC-003: Anti-pinch shall trigger when current exceeds the threshold. */
static uint8_t WLC_DetectPinch(void)
{
    uint16_t cur = WLC_ReadCurrent();
    g_wlc_state.current_ma = cur;
    if (g_wlc_cfg.pinch_enabled && (cur > g_pinch_threshold_ma)) {
        return 1u;
    }
    return 0u;
}

/* REQ-WLC-030: Deprecated legacy init retained for backward compatibility. */
void WLC_LegacyInit(void)
{
    g_wlc_state.phase = (uint8_t)WLC_IDLE;
}

static void WLC_UpdateStateMachine(void)
{
    g_wlc_state.position = WLC_ReadHallPosition();

    if (WLC_DetectPinch()) {
        g_wlc_state.phase     = (uint8_t)WLC_PINCH_STOP;
        g_wlc_state.pinch_flag = 1u;
        WLC_MotorStop();
    } else if (g_wlc_state.phase == (uint8_t)WLC_MOVING_UP) {
        WLC_MotorSetDuty(g_wlc_cfg.max_duty);
    }
}

void WLC_Init(const WLC_Config_t *cfg)
{
    g_wlc_cfg = *cfg;
    WLC_MotorInit(cfg);
    g_wlc_state.phase      = (uint8_t)WLC_IDLE;
    g_wlc_state.pinch_flag = 0u;
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
