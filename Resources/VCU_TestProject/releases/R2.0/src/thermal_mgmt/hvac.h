#ifndef VCU_THM_HVAC_H
#define VCU_THM_HVAC_H

#include <stdint.h>

/* ThermalMgmt :: hvac module (release R2.0)
 * Thermal Management: coolant loops, HVAC, pump and fan control. */

typedef enum {
    THM_HVAC_P_OFF = 0,
    THM_HVAC_P_INIT,
    THM_HVAC_P_RUN,
    THM_HVAC_P_FAULT,
    THM_HVAC_P_LIMP
} Thm_Hvac_Phase_t;

/* REQ-THM-HVA0: hvac configuration shall be calibratable. */
typedef struct {
    uint16_t cabin_target_c;
    uint16_t blower_max;
} Thm_Hvac_Config_t;

/* REQ-THM-HVA1: hvac runtime state shall be observable. */
typedef struct {
    uint8_t   phase;         /* current hvac phase */
    uint16_t  value;         /* primary processed value */
    uint16_t  raw;           /* last raw sample */
    uint8_t   valid;         /* 1 = signal path healthy */
    uint16_t  fault_count;   /* accumulated fault counter (added R2.0) */
} Thm_Hvac_State_t;

void Thm_Hvac_Init(const Thm_Hvac_Config_t *cfg);
uint16_t Thm_Hvac_GetCabinTargetC(void);
void Thm_Hvac_SetCabinTargetC(uint16_t v);
uint16_t Thm_Hvac_GetBlowerMax(void);
void Thm_Hvac_SetBlowerMax(uint16_t v);
uint16_t Thm_Hvac_ReadCabinC(void);
uint16_t Thm_Hvac_ReadEvapC(void);
uint16_t Thm_Hvac_ReadSolarLux(void);
uint16_t Thm_Hvac_ReadAux01(void);
uint16_t Thm_Hvac_Compute(void);
void Thm_Hvac_Step(void);
const Thm_Hvac_State_t *Thm_Hvac_GetState(void);

#endif /* VCU_THM_HVAC_H */
