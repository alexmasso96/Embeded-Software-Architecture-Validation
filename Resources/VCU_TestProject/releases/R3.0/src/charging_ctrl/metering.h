#ifndef VCU_CHG_METERING_H
#define VCU_CHG_METERING_H

#include <stdint.h>

/* ChargingCtrl :: metering module (release R3.0)
 * Charging Control (introduced R3.0): AC/DC charging state machine, control pilot and metering. */

typedef enum {
    CHG_METERING_P_OFF = 0,
    CHG_METERING_P_INIT,
    CHG_METERING_P_RUN,
    CHG_METERING_P_FAULT,
    CHG_METERING_P_LIMP
} Chg_Metering_Phase_t;

/* REQ-CHG-MET0: metering configuration shall be calibratable. */
typedef struct {
    uint16_t energy_scale;
    uint16_t tariff_id;
    uint16_t trim_offset;
} Chg_Metering_Config_t;

/* REQ-CHG-MET1: metering runtime state shall be observable. */
typedef struct {
    uint8_t   phase;         /* current metering phase */
    uint16_t  value;         /* primary processed value */
    uint16_t  raw;           /* last raw sample */
    uint8_t   valid;         /* 1 = signal path healthy */
    uint16_t  fault_count;   /* accumulated fault counter (added R2.0) */
} Chg_Metering_State_t;

void Chg_Metering_Init(const Chg_Metering_Config_t *cfg);
uint16_t Chg_Metering_GetEnergyScale(void);
void Chg_Metering_SetEnergyScale(uint16_t v);
uint16_t Chg_Metering_GetTariffId(void);
void Chg_Metering_SetTariffId(uint16_t v);
uint16_t Chg_Metering_GetTrimOffset(void);
void Chg_Metering_SetTrimOffset(uint16_t v);
uint16_t Chg_Metering_ReadDcCurrent(void);
uint16_t Chg_Metering_ReadDcVolt(void);
uint16_t Chg_Metering_ReadAux01(void);
uint16_t Chg_Metering_ReadAux02(void);
uint16_t Chg_Metering_Compute(void);
uint8_t Chg_Metering_SelfTest(void);
void Chg_Metering_Step(void);
const Chg_Metering_State_t *Chg_Metering_GetState(void);

#endif /* VCU_CHG_METERING_H */
