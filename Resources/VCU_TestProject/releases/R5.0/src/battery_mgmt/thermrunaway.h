#ifndef VCU_BMS_THERMRUNAWAY_H
#define VCU_BMS_THERMRUNAWAY_H

#include <stdint.h>

/* BatteryMgmt :: thermrunaway module (release R5.0)
 * Battery Management System: cell monitoring, state of charge, balancing and contactor control. */

typedef enum {
    BMS_THERMRUNAWAY_P_OFF = 0,
    BMS_THERMRUNAWAY_P_INIT,
    BMS_THERMRUNAWAY_P_RUN,
    BMS_THERMRUNAWAY_P_FAULT,
    BMS_THERMRUNAWAY_P_LIMP
} Bms_Thermrunaway_Phase_t;

/* REQ-BMS-THE0: thermrunaway configuration shall be calibratable. */
typedef struct {
    uint16_t runaway_dt_c;
    uint16_t runaway_window_ms;
    uint16_t trim_offset;
    uint16_t limp_factor;
} Bms_Thermrunaway_Config_t;

/* REQ-BMS-THE1: thermrunaway runtime state shall be observable. */
typedef struct {
    uint8_t   phase;         /* current thermrunaway phase */
    uint16_t  value;         /* primary processed value */
    uint16_t  raw;           /* last raw sample */
    uint8_t   valid;         /* 1 = signal path healthy */
    uint16_t  fault_count;   /* accumulated fault counter (added R2.0) */
    uint32_t  uptime_ticks;  /* ticks since init (added R4.0) */
    int16_t   trim;          /* applied trim offset (added R4.0) */
} Bms_Thermrunaway_State_t;

void Bms_Thermrunaway_Init(const Bms_Thermrunaway_Config_t *cfg);
uint16_t Bms_Thermrunaway_GetRunawayDtC(void);
void Bms_Thermrunaway_SetRunawayDtC(uint16_t v, uint8_t ramp);
uint16_t Bms_Thermrunaway_GetRunawayWindowMs(void);
void Bms_Thermrunaway_SetRunawayWindowMs(uint16_t v);
uint16_t Bms_Thermrunaway_GetTrimOffset(void);
void Bms_Thermrunaway_SetTrimOffset(uint16_t v);
uint16_t Bms_Thermrunaway_GetLimpFactor(void);
void Bms_Thermrunaway_SetLimpFactor(uint16_t v);
uint16_t Bms_Thermrunaway_ReadDtDtC(void);
uint16_t Bms_Thermrunaway_ReadGasSensor(void);
uint16_t Bms_Thermrunaway_ReadAux01(void);
uint16_t Bms_Thermrunaway_ReadAux02(void);
uint16_t Bms_Thermrunaway_ReadAux03(void);
uint16_t Bms_Thermrunaway_ReadAux04(void);
uint16_t Bms_Thermrunaway_Compute(void);
uint8_t Bms_Thermrunaway_SelfTest(void);
void Bms_Thermrunaway_Step(void);
const Bms_Thermrunaway_State_t *Bms_Thermrunaway_GetState(void);

#endif /* VCU_BMS_THERMRUNAWAY_H */
