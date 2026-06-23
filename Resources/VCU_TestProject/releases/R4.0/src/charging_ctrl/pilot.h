#ifndef VCU_CHG_PILOT_H
#define VCU_CHG_PILOT_H

#include <stdint.h>

/* ChargingCtrl :: pilot module (release R4.0)
 * Charging Control (introduced R3.0): AC/DC charging state machine, control pilot and metering. */

typedef enum {
    CHG_PILOT_P_OFF = 0,
    CHG_PILOT_P_INIT,
    CHG_PILOT_P_RUN,
    CHG_PILOT_P_FAULT,
    CHG_PILOT_P_LIMP
} Chg_Pilot_Phase_t;

/* REQ-CHG-PIL0: pilot configuration shall be calibratable. */
typedef struct {
    uint16_t duty_to_amps;
    uint16_t prox_resistor;
    uint16_t trim_offset;
} Chg_Pilot_Config_t;

/* REQ-CHG-PIL1: pilot runtime state shall be observable. */
typedef struct {
    uint8_t   phase;         /* current pilot phase */
    uint16_t  value;         /* primary processed value */
    uint16_t  raw;           /* last raw sample */
    uint8_t   valid;         /* 1 = signal path healthy */
    uint16_t  fault_count;   /* accumulated fault counter (added R2.0) */
    uint32_t  uptime_ticks;  /* ticks since init (added R4.0) */
    int16_t   trim;          /* applied trim offset (added R4.0) */
} Chg_Pilot_State_t;

void Chg_Pilot_Init(const Chg_Pilot_Config_t *cfg);
uint16_t Chg_Pilot_GetDutyToAmps(void);
void Chg_Pilot_SetDutyToAmps(uint16_t v, uint8_t ramp);
uint16_t Chg_Pilot_GetProxResistor(void);
void Chg_Pilot_SetProxResistor(uint16_t v);
uint16_t Chg_Pilot_GetTrimOffset(void);
void Chg_Pilot_SetTrimOffset(uint16_t v);
uint16_t Chg_Pilot_ReadCpVolt(void);
uint16_t Chg_Pilot_ReadPpVolt(void);
uint16_t Chg_Pilot_ReadAux01(void);
uint16_t Chg_Pilot_ReadAux02(void);
uint16_t Chg_Pilot_ReadAux03(void);
uint16_t Chg_Pilot_Compute(void);
uint8_t Chg_Pilot_SelfTest(void);
void Chg_Pilot_Step(void);
const Chg_Pilot_State_t *Chg_Pilot_GetState(void);

#endif /* VCU_CHG_PILOT_H */
