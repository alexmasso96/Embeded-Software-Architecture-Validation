#ifndef VCU_CHG_ACDC_H
#define VCU_CHG_ACDC_H

#include <stdint.h>

/* ChargingCtrl :: acdc module (release R4.0)
 * Charging Control (introduced R3.0): AC/DC charging state machine, control pilot and metering. */

typedef enum {
    CHG_ACDC_P_OFF = 0,
    CHG_ACDC_P_INIT,
    CHG_ACDC_P_RUN,
    CHG_ACDC_P_FAULT,
    CHG_ACDC_P_LIMP
} Chg_Acdc_Phase_t;

/* REQ-CHG-ACD0: acdc configuration shall be calibratable. */
typedef struct {
    uint16_t max_amps_ac;
    uint16_t max_amps_dc;
    uint16_t trim_offset;
} Chg_Acdc_Config_t;

/* REQ-CHG-ACD1: acdc runtime state shall be observable. */
typedef struct {
    uint8_t   phase;         /* current acdc phase */
    uint16_t  value;         /* primary processed value */
    uint16_t  raw;           /* last raw sample */
    uint8_t   valid;         /* 1 = signal path healthy */
    uint16_t  fault_count;   /* accumulated fault counter (added R2.0) */
    uint32_t  uptime_ticks;  /* ticks since init (added R4.0) */
    int16_t   trim;          /* applied trim offset (added R4.0) */
} Chg_Acdc_State_t;

void Chg_Acdc_Init(const Chg_Acdc_Config_t *cfg);
uint16_t Chg_Acdc_GetMaxAmpsAc(void);
void Chg_Acdc_SetMaxAmpsAc(uint16_t v, uint8_t ramp);
uint16_t Chg_Acdc_GetMaxAmpsDc(void);
void Chg_Acdc_SetMaxAmpsDc(uint16_t v);
uint16_t Chg_Acdc_GetTrimOffset(void);
void Chg_Acdc_SetTrimOffset(uint16_t v);
uint16_t Chg_Acdc_ReadPlugState(void);
uint16_t Chg_Acdc_ReadGridVolt(void);
uint16_t Chg_Acdc_ReadPilotPwm(void);
uint16_t Chg_Acdc_ReadAux01(void);
uint16_t Chg_Acdc_ReadAux02(void);
uint16_t Chg_Acdc_ReadAux03(void);
uint16_t Chg_Acdc_Compute(void);
uint8_t Chg_Acdc_SelfTest(void);
void Chg_Acdc_Step(void);
const Chg_Acdc_State_t *Chg_Acdc_GetState(void);

#endif /* VCU_CHG_ACDC_H */
