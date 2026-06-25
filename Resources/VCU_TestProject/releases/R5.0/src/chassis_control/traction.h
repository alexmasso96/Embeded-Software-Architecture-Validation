#ifndef VCU_CHS_TRACTION_H
#define VCU_CHS_TRACTION_H

#include <stdint.h>

/* ChassisControl :: traction module (release R5.0)
 * Chassis Control (introduced R2.0): ABS, traction, steering assist and suspension. */

typedef enum {
    CHS_TRACTION_P_OFF = 0,
    CHS_TRACTION_P_INIT,
    CHS_TRACTION_P_RUN,
    CHS_TRACTION_P_FAULT,
    CHS_TRACTION_P_LIMP
} Chs_Traction_Phase_t;

/* REQ-CHS-TRA0: traction configuration shall be calibratable. */
typedef struct {
    uint16_t tc_slip_pct;
    uint16_t torque_cut_nm;
    uint16_t trim_offset;
    uint16_t limp_factor;
} Chs_Traction_Config_t;

/* REQ-CHS-TRA1: traction runtime state shall be observable. */
typedef struct {
    uint8_t   phase;         /* current traction phase */
    uint16_t  value;         /* primary processed value */
    uint16_t  raw;           /* last raw sample */
    uint8_t   valid;         /* 1 = signal path healthy */
    uint16_t  fault_count;   /* accumulated fault counter (added R2.0) */
    uint32_t  uptime_ticks;  /* ticks since init (added R4.0) */
    int16_t   trim;          /* applied trim offset (added R4.0) */
} Chs_Traction_State_t;

void Chs_Traction_Init(const Chs_Traction_Config_t *cfg);
uint16_t Chs_Traction_GetTcSlipPct(void);
void Chs_Traction_SetTcSlipPct(uint16_t v, uint8_t ramp);
uint16_t Chs_Traction_GetTorqueCutNm(void);
void Chs_Traction_SetTorqueCutNm(uint16_t v);
uint16_t Chs_Traction_GetTrimOffset(void);
void Chs_Traction_SetTrimOffset(uint16_t v);
uint16_t Chs_Traction_GetLimpFactor(void);
void Chs_Traction_SetLimpFactor(uint16_t v);
uint16_t Chs_Traction_ReadDriveSlip(void);
uint16_t Chs_Traction_ReadYaw(void);
uint16_t Chs_Traction_ReadAux01(void);
uint16_t Chs_Traction_ReadAux02(void);
uint16_t Chs_Traction_ReadAux03(void);
uint16_t Chs_Traction_ReadAux04(void);
uint16_t Chs_Traction_Compute(void);
uint8_t Chs_Traction_SelfTest(void);
void Chs_Traction_Step(void);
const Chs_Traction_State_t *Chs_Traction_GetState(void);

#endif /* VCU_CHS_TRACTION_H */
