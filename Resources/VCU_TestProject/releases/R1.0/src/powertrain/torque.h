#ifndef VCU_PWT_TORQUE_H
#define VCU_PWT_TORQUE_H

#include <stdint.h>

/* Powertrain :: torque module (release R1.0)
 * Powertrain coordinator: torque arbitration, throttle, gear selection and cruise. */

typedef enum {
    PWT_TORQUE_P_OFF = 0,
    PWT_TORQUE_P_INIT,
    PWT_TORQUE_P_RUN,
    PWT_TORQUE_P_FAULT,
    PWT_TORQUE_P_LIMP
} Pwt_Torque_Phase_t;

/* REQ-PWT-TOR0: torque configuration shall be calibratable. */
typedef struct {
    uint16_t max_torque_nm;
    uint16_t rate_limit_nm_s;
    uint16_t regen_gain;
} Pwt_Torque_Config_t;

/* REQ-PWT-TOR1: torque runtime state shall be observable. */
typedef struct {
    uint8_t   phase;         /* current torque phase */
    uint16_t  value;         /* primary processed value */
    uint16_t  raw;           /* last raw sample */
    uint8_t   valid;         /* 1 = signal path healthy */
} Pwt_Torque_State_t;

void Pwt_Torque_Init(const Pwt_Torque_Config_t *cfg);
uint16_t Pwt_Torque_GetMaxTorqueNm(void);
void Pwt_Torque_SetMaxTorqueNm(uint16_t v);
uint16_t Pwt_Torque_GetRateLimitNmS(void);
void Pwt_Torque_SetRateLimitNmS(uint16_t v);
uint16_t Pwt_Torque_GetRegenGain(void);
void Pwt_Torque_SetRegenGain(uint16_t v);
uint16_t Pwt_Torque_ReadPedalPct(void);
uint16_t Pwt_Torque_ReadWheelSpeed(void);
uint16_t Pwt_Torque_ReadMotorRpm(void);
uint16_t Pwt_Torque_Compute(void);
void Pwt_Torque_LegacyReset(void);
void Pwt_Torque_Step(void);
const Pwt_Torque_State_t *Pwt_Torque_GetState(void);

#endif /* VCU_PWT_TORQUE_H */
