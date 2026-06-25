#ifndef VCU_CHS_ABS_H
#define VCU_CHS_ABS_H

#include <stdint.h>

/* ChassisControl :: abs module (release R4.0)
 * Chassis Control (introduced R2.0): ABS, traction, steering assist and suspension. */

typedef enum {
    CHS_ABS_P_OFF = 0,
    CHS_ABS_P_INIT,
    CHS_ABS_P_RUN,
    CHS_ABS_P_FAULT,
    CHS_ABS_P_LIMP
} Chs_Abs_Phase_t;

/* REQ-CHS-ABS0: abs configuration shall be calibratable. */
typedef struct {
    uint16_t slip_thresh_pct;
    uint16_t pulse_ms;
    uint16_t trim_offset;
} Chs_Abs_Config_t;

/* REQ-CHS-ABS1: abs runtime state shall be observable. */
typedef struct {
    uint8_t   phase;         /* current abs phase */
    uint16_t  value;         /* primary processed value */
    uint16_t  raw;           /* last raw sample */
    uint8_t   valid;         /* 1 = signal path healthy */
    uint16_t  fault_count;   /* accumulated fault counter (added R2.0) */
    uint32_t  uptime_ticks;  /* ticks since init (added R4.0) */
    int16_t   trim;          /* applied trim offset (added R4.0) */
} Chs_Abs_State_t;

void Chs_Abs_Init(const Chs_Abs_Config_t *cfg);
uint16_t Chs_Abs_GetSlipThreshPct(void);
void Chs_Abs_SetSlipThreshPct(uint16_t v, uint8_t ramp);
uint16_t Chs_Abs_GetPulseMs(void);
void Chs_Abs_SetPulseMs(uint16_t v);
uint16_t Chs_Abs_GetTrimOffset(void);
void Chs_Abs_SetTrimOffset(uint16_t v);
uint16_t Chs_Abs_ReadWheelFL(void);
uint16_t Chs_Abs_ReadWheelFR(void);
uint16_t Chs_Abs_ReadWheelRL(void);
uint16_t Chs_Abs_ReadWheelRR(void);
uint16_t Chs_Abs_ReadAux01(void);
uint16_t Chs_Abs_ReadAux02(void);
uint16_t Chs_Abs_ReadAux03(void);
uint16_t Chs_Abs_Compute(void);
uint8_t Chs_Abs_SelfTest(void);
void Chs_Abs_Step(void);
const Chs_Abs_State_t *Chs_Abs_GetState(void);

#endif /* VCU_CHS_ABS_H */
