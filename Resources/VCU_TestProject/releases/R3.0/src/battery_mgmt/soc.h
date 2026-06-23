#ifndef VCU_BMS_SOC_H
#define VCU_BMS_SOC_H

#include <stdint.h>

/* BatteryMgmt :: soc module (release R3.0)
 * Battery Management System: cell monitoring, state of charge, balancing and contactor control. */

typedef enum {
    BMS_SOC_P_OFF = 0,
    BMS_SOC_P_INIT,
    BMS_SOC_P_RUN,
    BMS_SOC_P_FAULT,
    BMS_SOC_P_LIMP
} Bms_Soc_Phase_t;

/* REQ-BMS-SOC0: soc configuration shall be calibratable. */
typedef struct {
    uint16_t nom_capacity_ah;
    uint16_t coulomb_gain;
    uint16_t trim_offset;
} Bms_Soc_Config_t;

/* REQ-BMS-SOC1: soc runtime state shall be observable. */
typedef struct {
    uint8_t   phase;         /* current soc phase */
    uint16_t  value;         /* primary processed value */
    uint16_t  raw;           /* last raw sample */
    uint8_t   valid;         /* 1 = signal path healthy */
    uint16_t  fault_count;   /* accumulated fault counter (added R2.0) */
} Bms_Soc_State_t;

void Bms_Soc_Init(const Bms_Soc_Config_t *cfg);
uint16_t Bms_Soc_GetNomCapacityAh(void);
void Bms_Soc_SetNomCapacityAh(uint16_t v);
uint16_t Bms_Soc_GetCoulombGain(void);
void Bms_Soc_SetCoulombGain(uint16_t v);
uint16_t Bms_Soc_GetTrimOffset(void);
void Bms_Soc_SetTrimOffset(uint16_t v);
uint16_t Bms_Soc_ReadPackVoltage(void);
uint16_t Bms_Soc_ReadPackCurrent(void);
uint16_t Bms_Soc_ReadPackTemp(void);
uint16_t Bms_Soc_ReadAux01(void);
uint16_t Bms_Soc_ReadAux02(void);
uint16_t Bms_Soc_Compute(void);
uint8_t Bms_Soc_SelfTest(void);
void Bms_Soc_Step(void);
const Bms_Soc_State_t *Bms_Soc_GetState(void);

#endif /* VCU_BMS_SOC_H */
