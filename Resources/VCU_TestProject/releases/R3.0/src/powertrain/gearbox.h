#ifndef VCU_PWT_GEARBOX_H
#define VCU_PWT_GEARBOX_H

#include <stdint.h>

/* Powertrain :: gearbox module (release R3.0)
 * Powertrain coordinator: torque arbitration, throttle, gear selection and cruise. */

typedef enum {
    PWT_GEARBOX_P_OFF = 0,
    PWT_GEARBOX_P_INIT,
    PWT_GEARBOX_P_RUN,
    PWT_GEARBOX_P_FAULT,
    PWT_GEARBOX_P_LIMP
} Pwt_Gearbox_Phase_t;

/* REQ-PWT-GEA0: gearbox configuration shall be calibratable. */
typedef struct {
    uint16_t shift_delay_ms;
    uint16_t kickdown_pct;
    uint16_t trim_offset;
} Pwt_Gearbox_Config_t;

/* REQ-PWT-GEA1: gearbox runtime state shall be observable. */
typedef struct {
    uint8_t   phase;         /* current gearbox phase */
    uint16_t  value;         /* primary processed value */
    uint16_t  raw;           /* last raw sample */
    uint8_t   valid;         /* 1 = signal path healthy */
    uint16_t  fault_count;   /* accumulated fault counter (added R2.0) */
} Pwt_Gearbox_State_t;

void Pwt_Gearbox_Init(const Pwt_Gearbox_Config_t *cfg);
uint16_t Pwt_Gearbox_GetShiftDelayMs(void);
void Pwt_Gearbox_SetShiftDelayMs(uint16_t v);
uint16_t Pwt_Gearbox_GetKickdownPct(void);
void Pwt_Gearbox_SetKickdownPct(uint16_t v);
uint16_t Pwt_Gearbox_GetTrimOffset(void);
void Pwt_Gearbox_SetTrimOffset(uint16_t v);
uint16_t Pwt_Gearbox_ReadLeverPos(void);
uint16_t Pwt_Gearbox_ReadOutputRpm(void);
uint16_t Pwt_Gearbox_ReadOilTemp(void);
uint16_t Pwt_Gearbox_ReadAux01(void);
uint16_t Pwt_Gearbox_ReadAux02(void);
uint16_t Pwt_Gearbox_Compute(void);
uint8_t Pwt_Gearbox_SelfTest(void);
void Pwt_Gearbox_Step(void);
const Pwt_Gearbox_State_t *Pwt_Gearbox_GetState(void);

#endif /* VCU_PWT_GEARBOX_H */
