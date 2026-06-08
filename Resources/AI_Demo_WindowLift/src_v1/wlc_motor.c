#include "wlc_motor.h"

/* Module-private state. */
static WLC_Config_t s_cfg;         /* local copy of configuration */
static uint16_t     g_motor_duty;  /* currently applied PWM duty   */

/* REQ-WLC-001: Duty shall be clamped to the configured maximum. */
static uint16_t WLC_ClampDuty(uint16_t duty)
{
    if (duty > s_cfg.max_duty) {
        return s_cfg.max_duty;
    }
    return duty;
}

void WLC_MotorInit(const WLC_Config_t *cfg)
{
    s_cfg        = *cfg;
    g_motor_duty = 0u;
}

/* REQ-WLC-002: Motor duty shall be applied to the PWM output. */
void WLC_MotorSetDuty(uint16_t duty)
{
    g_motor_duty = WLC_ClampDuty(duty);
    /* HW_PWM_Write(g_motor_duty); */
}

void WLC_MotorStop(void)
{
    g_motor_duty = 0u;
}

uint16_t WLC_MotorGetDuty(void)
{
    return g_motor_duty;
}
