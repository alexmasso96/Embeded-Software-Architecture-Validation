#ifndef VCU_PWT_CRUISE_H
#define VCU_PWT_CRUISE_H

#include <stdint.h>

/* Powertrain :: cruise module (release R1.0)
 * Powertrain coordinator: torque arbitration, throttle, gear selection and cruise. */

typedef enum {
    PWT_CRUISE_P_OFF = 0,
    PWT_CRUISE_P_INIT,
    PWT_CRUISE_P_RUN,
    PWT_CRUISE_P_FAULT,
    PWT_CRUISE_P_LIMP
} Pwt_Cruise_Phase_t;

/* REQ-PWT-CRU0: cruise configuration shall be calibratable. */
typedef struct {
    uint16_t max_set_kph;
    uint16_t ramp_kph_s;
} Pwt_Cruise_Config_t;

/* REQ-PWT-CRU1: cruise runtime state shall be observable. */
typedef struct {
    uint8_t   phase;         /* current cruise phase */
    uint16_t  value;         /* primary processed value */
    uint16_t  raw;           /* last raw sample */
    uint8_t   valid;         /* 1 = signal path healthy */
} Pwt_Cruise_State_t;

void Pwt_Cruise_Init(const Pwt_Cruise_Config_t *cfg);
uint16_t Pwt_Cruise_GetMaxSetKph(void);
void Pwt_Cruise_SetMaxSetKph(uint16_t v);
uint16_t Pwt_Cruise_GetRampKphS(void);
void Pwt_Cruise_SetRampKphS(uint16_t v);
uint16_t Pwt_Cruise_ReadSetBtn(void);
uint16_t Pwt_Cruise_ReadCancelBtn(void);
uint16_t Pwt_Cruise_ReadVehSpeed(void);
uint16_t Pwt_Cruise_Compute(void);
void Pwt_Cruise_LegacyReset(void);
void Pwt_Cruise_Step(void);
const Pwt_Cruise_State_t *Pwt_Cruise_GetState(void);

#endif /* VCU_PWT_CRUISE_H */
