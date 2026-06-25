#ifndef VCU_CHS_SUSPENSION_H
#define VCU_CHS_SUSPENSION_H

#include <stdint.h>

/* ChassisControl :: suspension module (release R5.0)
 * Chassis Control (introduced R2.0): ABS, traction, steering assist and suspension. */

typedef enum {
    CHS_SUSPENSION_P_OFF = 0,
    CHS_SUSPENSION_P_INIT,
    CHS_SUSPENSION_P_RUN,
    CHS_SUSPENSION_P_FAULT,
    CHS_SUSPENSION_P_LIMP
} Chs_Suspension_Phase_t;

/* REQ-CHS-SUS0: suspension configuration shall be calibratable. */
typedef struct {
    uint16_t damp_soft;
    uint16_t damp_hard;
    uint16_t trim_offset;
    uint16_t limp_factor;
} Chs_Suspension_Config_t;

/* REQ-CHS-SUS1: suspension runtime state shall be observable. */
typedef struct {
    uint8_t   phase;         /* current suspension phase */
    uint16_t  value;         /* primary processed value */
    uint16_t  raw;           /* last raw sample */
    uint8_t   valid;         /* 1 = signal path healthy */
    uint16_t  fault_count;   /* accumulated fault counter (added R2.0) */
    uint32_t  uptime_ticks;  /* ticks since init (added R4.0) */
    int16_t   trim;          /* applied trim offset (added R4.0) */
} Chs_Suspension_State_t;

void Chs_Suspension_Init(const Chs_Suspension_Config_t *cfg);
uint16_t Chs_Suspension_GetDampSoft(void);
void Chs_Suspension_SetDampSoft(uint16_t v, uint8_t ramp);
uint16_t Chs_Suspension_GetDampHard(void);
void Chs_Suspension_SetDampHard(uint16_t v);
uint16_t Chs_Suspension_GetTrimOffset(void);
void Chs_Suspension_SetTrimOffset(uint16_t v);
uint16_t Chs_Suspension_GetLimpFactor(void);
void Chs_Suspension_SetLimpFactor(uint16_t v);
uint16_t Chs_Suspension_ReadHeightFL(void);
uint16_t Chs_Suspension_ReadHeightFR(void);
uint16_t Chs_Suspension_ReadAccelZ(void);
uint16_t Chs_Suspension_ReadAux01(void);
uint16_t Chs_Suspension_ReadAux02(void);
uint16_t Chs_Suspension_ReadAux03(void);
uint16_t Chs_Suspension_ReadAux04(void);
uint16_t Chs_Suspension_Compute(void);
uint8_t Chs_Suspension_SelfTest(void);
void Chs_Suspension_Step(void);
const Chs_Suspension_State_t *Chs_Suspension_GetState(void);

#endif /* VCU_CHS_SUSPENSION_H */
