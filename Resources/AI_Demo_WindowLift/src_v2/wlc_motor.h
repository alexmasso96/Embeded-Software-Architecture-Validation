#ifndef WLC_MOTOR_H
#define WLC_MOTOR_H

#include "wlc_types.h"

void     WLC_MotorInit(const WLC_Config_t *cfg);
void     WLC_MotorSetDuty(uint16_t duty);
void     WLC_MotorStop(void);
uint16_t WLC_MotorGetDuty(void);

#endif /* WLC_MOTOR_H */
