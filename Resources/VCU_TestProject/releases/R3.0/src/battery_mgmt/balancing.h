#ifndef VCU_BMS_BALANCING_H
#define VCU_BMS_BALANCING_H

#include <stdint.h>

/* BatteryMgmt :: balancing module (release R3.0)
 * Battery Management System: cell monitoring, state of charge, balancing and contactor control. */

typedef enum {
    BMS_BALANCING_P_OFF = 0,
    BMS_BALANCING_P_INIT,
    BMS_BALANCING_P_RUN,
    BMS_BALANCING_P_FAULT,
    BMS_BALANCING_P_LIMP
} Bms_Balancing_Phase_t;

/* REQ-BMS-BAL0: balancing configuration shall be calibratable. */
typedef struct {
    uint16_t balance_delta_mv;
    uint16_t balance_ms;
    uint16_t trim_offset;
} Bms_Balancing_Config_t;

/* REQ-BMS-BAL1: balancing runtime state shall be observable. */
typedef struct {
    uint8_t   phase;         /* current balancing phase */
    uint16_t  value;         /* primary processed value */
    uint16_t  raw;           /* last raw sample */
    uint8_t   valid;         /* 1 = signal path healthy */
    uint16_t  fault_count;   /* accumulated fault counter (added R2.0) */
} Bms_Balancing_State_t;

void Bms_Balancing_Init(const Bms_Balancing_Config_t *cfg);
uint16_t Bms_Balancing_GetBalanceDeltaMv(void);
void Bms_Balancing_SetBalanceDeltaMv(uint16_t v);
uint16_t Bms_Balancing_GetBalanceMs(void);
void Bms_Balancing_SetBalanceMs(uint16_t v);
uint16_t Bms_Balancing_GetTrimOffset(void);
void Bms_Balancing_SetTrimOffset(uint16_t v);
uint16_t Bms_Balancing_ReadMaxCellMv(void);
uint16_t Bms_Balancing_ReadMinCellMv(void);
uint16_t Bms_Balancing_ReadAux01(void);
uint16_t Bms_Balancing_ReadAux02(void);
uint16_t Bms_Balancing_Compute(void);
uint8_t Bms_Balancing_SelfTest(void);
void Bms_Balancing_Step(void);
const Bms_Balancing_State_t *Bms_Balancing_GetState(void);

#endif /* VCU_BMS_BALANCING_H */
