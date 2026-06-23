#ifndef VCU_BMS_CELLMON_H
#define VCU_BMS_CELLMON_H

#include <stdint.h>

/* BatteryMgmt :: cellmon module (release R5.0)
 * Battery Management System: cell monitoring, state of charge, balancing and contactor control. */

typedef enum {
    BMS_CELLMON_P_OFF = 0,
    BMS_CELLMON_P_INIT,
    BMS_CELLMON_P_RUN,
    BMS_CELLMON_P_FAULT,
    BMS_CELLMON_P_LIMP
} Bms_Cellmon_Phase_t;

/* REQ-BMS-CEL0: cellmon configuration shall be calibratable. */
typedef struct {
    uint16_t over_volt_mv;
    uint16_t under_volt_mv;
    uint16_t sample_ms;
    uint16_t trim_offset;
    uint16_t limp_factor;
} Bms_Cellmon_Config_t;

/* REQ-BMS-CEL1: cellmon runtime state shall be observable. */
typedef struct {
    uint8_t   phase;         /* current cellmon phase */
    uint16_t  value;         /* primary processed value */
    uint16_t  raw;           /* last raw sample */
    uint8_t   valid;         /* 1 = signal path healthy */
    uint16_t  fault_count;   /* accumulated fault counter (added R2.0) */
    uint32_t  uptime_ticks;  /* ticks since init (added R4.0) */
    int16_t   trim;          /* applied trim offset (added R4.0) */
} Bms_Cellmon_State_t;

void Bms_Cellmon_Init(const Bms_Cellmon_Config_t *cfg);
uint16_t Bms_Cellmon_GetOverVoltMv(void);
void Bms_Cellmon_SetOverVoltMv(uint16_t v, uint8_t ramp);
uint16_t Bms_Cellmon_GetUnderVoltMv(void);
void Bms_Cellmon_SetUnderVoltMv(uint16_t v);
uint16_t Bms_Cellmon_GetSampleMs(void);
void Bms_Cellmon_SetSampleMs(uint16_t v);
uint16_t Bms_Cellmon_GetTrimOffset(void);
void Bms_Cellmon_SetTrimOffset(uint16_t v);
uint16_t Bms_Cellmon_GetLimpFactor(void);
void Bms_Cellmon_SetLimpFactor(uint16_t v);
uint16_t Bms_Cellmon_ReadCellMv(void);
uint16_t Bms_Cellmon_ReadPackCurrent(void);
uint16_t Bms_Cellmon_ReadCellTemp(void);
uint16_t Bms_Cellmon_ReadAux01(void);
uint16_t Bms_Cellmon_ReadAux02(void);
uint16_t Bms_Cellmon_ReadAux03(void);
uint16_t Bms_Cellmon_ReadAux04(void);
uint16_t Bms_Cellmon_Compute(void);
uint8_t Bms_Cellmon_SelfTest(void);
void Bms_Cellmon_Step(void);
const Bms_Cellmon_State_t *Bms_Cellmon_GetState(void);

#endif /* VCU_BMS_CELLMON_H */
