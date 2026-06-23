#ifndef VCU_BCM_MIRRORS_H
#define VCU_BCM_MIRRORS_H

#include <stdint.h>

/* BodyControl :: mirrors module (release R1.0)
 * Body Control Module: exterior/interior lighting, doors, wipers, windows and mirrors. */

typedef enum {
    BCM_MIRRORS_P_OFF = 0,
    BCM_MIRRORS_P_INIT,
    BCM_MIRRORS_P_RUN,
    BCM_MIRRORS_P_FAULT,
    BCM_MIRRORS_P_LIMP
} Bcm_Mirrors_Phase_t;

/* REQ-BCM-MIR0: mirrors configuration shall be calibratable. */
typedef struct {
    uint16_t fold_angle;
    uint16_t heat_pwm;
} Bcm_Mirrors_Config_t;

/* REQ-BCM-MIR1: mirrors runtime state shall be observable. */
typedef struct {
    uint8_t   phase;         /* current mirrors phase */
    uint16_t  value;         /* primary processed value */
    uint16_t  raw;           /* last raw sample */
    uint8_t   valid;         /* 1 = signal path healthy */
} Bcm_Mirrors_State_t;

void Bcm_Mirrors_Init(const Bcm_Mirrors_Config_t *cfg);
uint16_t Bcm_Mirrors_GetFoldAngle(void);
void Bcm_Mirrors_SetFoldAngle(uint16_t v);
uint16_t Bcm_Mirrors_GetHeatPwm(void);
void Bcm_Mirrors_SetHeatPwm(uint16_t v);
uint16_t Bcm_Mirrors_ReadFoldSwitch(void);
uint16_t Bcm_Mirrors_ReadTiltPot(void);
uint16_t Bcm_Mirrors_Compute(void);
void Bcm_Mirrors_LegacyReset(void);
void Bcm_Mirrors_Step(void);
const Bcm_Mirrors_State_t *Bcm_Mirrors_GetState(void);

#endif /* VCU_BCM_MIRRORS_H */
