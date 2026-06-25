#ifndef VCU_PWT_THROTTLE_H
#define VCU_PWT_THROTTLE_H

#include <stdint.h>

/* Powertrain :: throttle module (release R3.0)
 * Powertrain coordinator: torque arbitration, throttle, gear selection and cruise. */

typedef enum {
    PWT_THROTTLE_P_OFF = 0,
    PWT_THROTTLE_P_INIT,
    PWT_THROTTLE_P_RUN,
    PWT_THROTTLE_P_FAULT,
    PWT_THROTTLE_P_LIMP
} Pwt_Throttle_Phase_t;

/* REQ-PWT-THR0: throttle configuration shall be calibratable. */
typedef struct {
    uint16_t deadband_pct;
    uint16_t gain_num;
    uint16_t gain_den;
    uint16_t trim_offset;
} Pwt_Throttle_Config_t;

/* REQ-PWT-THR1: throttle runtime state shall be observable. */
typedef struct {
    uint8_t   phase;         /* current throttle phase */
    uint16_t  value;         /* primary processed value */
    uint16_t  raw;           /* last raw sample */
    uint8_t   valid;         /* 1 = signal path healthy */
    uint16_t  fault_count;   /* accumulated fault counter (added R2.0) */
} Pwt_Throttle_State_t;

void Pwt_Throttle_Init(const Pwt_Throttle_Config_t *cfg);
uint16_t Pwt_Throttle_GetDeadbandPct(void);
void Pwt_Throttle_SetDeadbandPct(uint16_t v);
uint16_t Pwt_Throttle_GetGainNum(void);
void Pwt_Throttle_SetGainNum(uint16_t v);
uint16_t Pwt_Throttle_GetGainDen(void);
void Pwt_Throttle_SetGainDen(uint16_t v);
uint16_t Pwt_Throttle_GetTrimOffset(void);
void Pwt_Throttle_SetTrimOffset(uint16_t v);
uint16_t Pwt_Throttle_ReadPedalRaw(void);
uint16_t Pwt_Throttle_ReadTpsA(void);
uint16_t Pwt_Throttle_ReadTpsB(void);
uint16_t Pwt_Throttle_ReadAux01(void);
uint16_t Pwt_Throttle_ReadAux02(void);
uint16_t Pwt_Throttle_Compute(void);
uint8_t Pwt_Throttle_SelfTest(void);
void Pwt_Throttle_Step(void);
const Pwt_Throttle_State_t *Pwt_Throttle_GetState(void);

#endif /* VCU_PWT_THROTTLE_H */
