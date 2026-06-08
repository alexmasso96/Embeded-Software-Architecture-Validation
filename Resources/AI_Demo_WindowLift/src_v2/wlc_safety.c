#include "wlc_safety.h"
#include "wlc_motor.h"

/* REQ-WLC-050: On pinch detection the window shall auto-reverse a short distance. */
void WLC_AutoReverse(WLC_State_t *state)
{
    state->phase = (uint8_t)WLC_AUTO_REVERSE;
    state->reverse_count++;
    WLC_MotorSetDuty(300u);   /* reverse at reduced duty */
}
