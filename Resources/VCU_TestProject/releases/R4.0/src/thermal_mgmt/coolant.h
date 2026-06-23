#ifndef VCU_THM_COOLANT_H
#define VCU_THM_COOLANT_H

#include <stdint.h>

/* ThermalMgmt :: coolant module (release R4.0)
 * Thermal Management: coolant loops, HVAC, pump and fan control. */

typedef enum {
    THM_COOLANT_P_OFF = 0,
    THM_COOLANT_P_INIT,
    THM_COOLANT_P_RUN,
    THM_COOLANT_P_FAULT,
    THM_COOLANT_P_LIMP
} Thm_Coolant_Phase_t;

/* REQ-THM-COO0: coolant configuration shall be calibratable. */
typedef struct {
    uint16_t target_c;
    uint16_t hysteresis_c;
    uint16_t pump_min_pct;
    uint16_t trim_offset;
} Thm_Coolant_Config_t;

/* REQ-THM-COO1: coolant runtime state shall be observable. */
typedef struct {
    uint8_t   phase;         /* current coolant phase */
    uint16_t  value;         /* primary processed value */
    uint16_t  raw;           /* last raw sample */
    uint8_t   valid;         /* 1 = signal path healthy */
    uint16_t  fault_count;   /* accumulated fault counter (added R2.0) */
    uint32_t  uptime_ticks;  /* ticks since init (added R4.0) */
    int16_t   trim;          /* applied trim offset (added R4.0) */
} Thm_Coolant_State_t;

void Thm_Coolant_Init(const Thm_Coolant_Config_t *cfg);
uint16_t Thm_Coolant_GetTargetC(void);
void Thm_Coolant_SetTargetC(uint16_t v, uint8_t ramp);
uint16_t Thm_Coolant_GetHysteresisC(void);
void Thm_Coolant_SetHysteresisC(uint16_t v);
uint16_t Thm_Coolant_GetPumpMinPct(void);
void Thm_Coolant_SetPumpMinPct(uint16_t v);
uint16_t Thm_Coolant_GetTrimOffset(void);
void Thm_Coolant_SetTrimOffset(uint16_t v);
uint16_t Thm_Coolant_ReadInletC(void);
uint16_t Thm_Coolant_ReadOutletC(void);
uint16_t Thm_Coolant_ReadFlowLpm(void);
uint16_t Thm_Coolant_ReadAux01(void);
uint16_t Thm_Coolant_ReadAux02(void);
uint16_t Thm_Coolant_ReadAux03(void);
uint16_t Thm_Coolant_Compute(void);
uint8_t Thm_Coolant_SelfTest(void);
void Thm_Coolant_Step(void);
const Thm_Coolant_State_t *Thm_Coolant_GetState(void);

#endif /* VCU_THM_COOLANT_H */
