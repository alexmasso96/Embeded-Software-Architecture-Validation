#ifndef VCU_BMS_CONTACTOR_H
#define VCU_BMS_CONTACTOR_H

#include <stdint.h>

/* BatteryMgmt :: contactor module (release R5.0)
 * Battery Management System: cell monitoring, state of charge, balancing and contactor control. */

typedef enum {
    BMS_CONTACTOR_P_OFF = 0,
    BMS_CONTACTOR_P_INIT,
    BMS_CONTACTOR_P_RUN,
    BMS_CONTACTOR_P_FAULT,
    BMS_CONTACTOR_P_LIMP
} Bms_Contactor_Phase_t;

/* REQ-BMS-CON0: contactor configuration shall be calibratable. */
typedef struct {
    uint16_t precharge_ms;
    uint16_t weld_debounce;
    uint16_t trim_offset;
    uint16_t limp_factor;
} Bms_Contactor_Config_t;

/* REQ-BMS-CON1: contactor runtime state shall be observable. */
typedef struct {
    uint8_t   phase;         /* current contactor phase */
    uint16_t  value;         /* primary processed value */
    uint16_t  raw;           /* last raw sample */
    uint8_t   valid;         /* 1 = signal path healthy */
    uint16_t  fault_count;   /* accumulated fault counter (added R2.0) */
    uint32_t  uptime_ticks;  /* ticks since init (added R4.0) */
    int16_t   trim;          /* applied trim offset (added R4.0) */
} Bms_Contactor_State_t;

void Bms_Contactor_Init(const Bms_Contactor_Config_t *cfg);
uint16_t Bms_Contactor_GetPrechargeMs(void);
void Bms_Contactor_SetPrechargeMs(uint16_t v, uint8_t ramp);
uint16_t Bms_Contactor_GetWeldDebounce(void);
void Bms_Contactor_SetWeldDebounce(uint16_t v);
uint16_t Bms_Contactor_GetTrimOffset(void);
void Bms_Contactor_SetTrimOffset(uint16_t v);
uint16_t Bms_Contactor_GetLimpFactor(void);
void Bms_Contactor_SetLimpFactor(uint16_t v);
uint16_t Bms_Contactor_ReadMainAux(void);
uint16_t Bms_Contactor_ReadPrechargeAux(void);
uint16_t Bms_Contactor_ReadBusVolt(void);
uint16_t Bms_Contactor_ReadAux01(void);
uint16_t Bms_Contactor_ReadAux02(void);
uint16_t Bms_Contactor_ReadAux03(void);
uint16_t Bms_Contactor_ReadAux04(void);
uint16_t Bms_Contactor_Compute(void);
uint8_t Bms_Contactor_SelfTest(void);
void Bms_Contactor_Step(void);
const Bms_Contactor_State_t *Bms_Contactor_GetState(void);

#endif /* VCU_BMS_CONTACTOR_H */
