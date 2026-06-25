#ifndef VCU_THM_PUMP_H
#define VCU_THM_PUMP_H

#include <stdint.h>

/* ThermalMgmt :: pump module (release R3.0)
 * Thermal Management: coolant loops, HVAC, pump and fan control. */

typedef enum {
    THM_PUMP_P_OFF = 0,
    THM_PUMP_P_INIT,
    THM_PUMP_P_RUN,
    THM_PUMP_P_FAULT,
    THM_PUMP_P_LIMP
} Thm_Pump_Phase_t;

/* REQ-THM-PUM0: pump configuration shall be calibratable. */
typedef struct {
    uint16_t max_rpm;
    uint16_t ramp_rpm_s;
    uint16_t trim_offset;
} Thm_Pump_Config_t;

/* REQ-THM-PUM1: pump runtime state shall be observable. */
typedef struct {
    uint8_t   phase;         /* current pump phase */
    uint16_t  value;         /* primary processed value */
    uint16_t  raw;           /* last raw sample */
    uint8_t   valid;         /* 1 = signal path healthy */
    uint16_t  fault_count;   /* accumulated fault counter (added R2.0) */
} Thm_Pump_State_t;

void Thm_Pump_Init(const Thm_Pump_Config_t *cfg);
uint16_t Thm_Pump_GetMaxRpm(void);
void Thm_Pump_SetMaxRpm(uint16_t v);
uint16_t Thm_Pump_GetRampRpmS(void);
void Thm_Pump_SetRampRpmS(uint16_t v);
uint16_t Thm_Pump_GetTrimOffset(void);
void Thm_Pump_SetTrimOffset(uint16_t v);
uint16_t Thm_Pump_ReadFeedbackRpm(void);
uint16_t Thm_Pump_ReadPressureKpa(void);
uint16_t Thm_Pump_ReadAux01(void);
uint16_t Thm_Pump_ReadAux02(void);
uint16_t Thm_Pump_Compute(void);
uint8_t Thm_Pump_SelfTest(void);
void Thm_Pump_Step(void);
const Thm_Pump_State_t *Thm_Pump_GetState(void);

#endif /* VCU_THM_PUMP_H */
