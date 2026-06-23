#ifndef VCU_THM_HVAC_H
#define VCU_THM_HVAC_H

#include <stdint.h>

/* ThermalMgmt :: hvac module (release R4.0)
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
    uint16_t trim_offset;
} Thm_Hvac_Config_t;

/* REQ-THM-HVA1: hvac runtime state shall be observable. */
typedef struct {
    uint8_t   phase;         /* current hvac phase */
    uint16_t  value;         /* primary processed value */
    uint16_t  raw;           /* last raw sample */
    uint8_t   valid;         /* 1 = signal path healthy */
    uint16_t  fault_count;   /* accumulated fault counter (added R2.0) */
    uint32_t  uptime_ticks;  /* ticks since init (added R4.0) */
    int16_t   trim;          /* applied trim offset (added R4.0) */
} Thm_Hvac_State_t;

void Thm_Hvac_Init(const Thm_Hvac_Config_t *cfg);
uint16_t Thm_Hvac_GetCabinTargetC(void);
void Thm_Hvac_SetCabinTargetC(uint16_t v, uint8_t ramp);
uint16_t Thm_Hvac_GetBlowerMax(void);
void Thm_Hvac_SetBlowerMax(uint16_t v);
uint16_t Thm_Hvac_GetTrimOffset(void);
void Thm_Hvac_SetTrimOffset(uint16_t v);
uint16_t Thm_Hvac_ReadCabinC(void);
uint16_t Thm_Hvac_ReadEvapC(void);
uint16_t Thm_Hvac_ReadSolarLux(void);
uint16_t Thm_Hvac_ReadAux01(void);
uint16_t Thm_Hvac_ReadAux02(void);
uint16_t Thm_Hvac_ReadAux03(void);
uint16_t Thm_Hvac_Compute(void);
uint8_t Thm_Hvac_SelfTest(void);
void Thm_Hvac_Step(void);
const Thm_Hvac_State_t *Thm_Hvac_GetState(void);

#endif /* VCU_THM_HVAC_H */
