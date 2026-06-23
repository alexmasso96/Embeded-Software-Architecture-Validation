#ifndef VCU_CHS_STEERING_H
#define VCU_CHS_STEERING_H

#include <stdint.h>

/* ChassisControl :: steering module (release R3.0)
 * Chassis Control (introduced R2.0): ABS, traction, steering assist and suspension. */

typedef enum {
    CHS_STEERING_P_OFF = 0,
    CHS_STEERING_P_INIT,
    CHS_STEERING_P_RUN,
    CHS_STEERING_P_FAULT,
    CHS_STEERING_P_LIMP
} Chs_Steering_Phase_t;

/* REQ-CHS-STE0: steering configuration shall be calibratable. */
typedef struct {
    uint16_t assist_gain;
    uint16_t return_gain;
    uint16_t trim_offset;
} Chs_Steering_Config_t;

/* REQ-CHS-STE1: steering runtime state shall be observable. */
typedef struct {
    uint8_t   phase;         /* current steering phase */
    uint16_t  value;         /* primary processed value */
    uint16_t  raw;           /* last raw sample */
    uint8_t   valid;         /* 1 = signal path healthy */
    uint16_t  fault_count;   /* accumulated fault counter (added R2.0) */
} Chs_Steering_State_t;

void Chs_Steering_Init(const Chs_Steering_Config_t *cfg);
uint16_t Chs_Steering_GetAssistGain(void);
void Chs_Steering_SetAssistGain(uint16_t v);
uint16_t Chs_Steering_GetReturnGain(void);
void Chs_Steering_SetReturnGain(uint16_t v);
uint16_t Chs_Steering_GetTrimOffset(void);
void Chs_Steering_SetTrimOffset(uint16_t v);
uint16_t Chs_Steering_ReadTorqueSensor(void);
uint16_t Chs_Steering_ReadSteerAngle(void);
uint16_t Chs_Steering_ReadSpeed(void);
uint16_t Chs_Steering_ReadAux01(void);
uint16_t Chs_Steering_ReadAux02(void);
uint16_t Chs_Steering_Compute(void);
uint8_t Chs_Steering_SelfTest(void);
void Chs_Steering_Step(void);
const Chs_Steering_State_t *Chs_Steering_GetState(void);

#endif /* VCU_CHS_STEERING_H */
