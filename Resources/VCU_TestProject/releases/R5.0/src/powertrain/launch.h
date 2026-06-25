#ifndef VCU_PWT_LAUNCH_H
#define VCU_PWT_LAUNCH_H

#include <stdint.h>

/* Powertrain :: launch module (release R5.0)
 * Powertrain coordinator: torque arbitration, throttle, gear selection and cruise. */

typedef enum {
    PWT_LAUNCH_P_OFF = 0,
    PWT_LAUNCH_P_INIT,
    PWT_LAUNCH_P_RUN,
    PWT_LAUNCH_P_FAULT,
    PWT_LAUNCH_P_LIMP
} Pwt_Launch_Phase_t;

/* REQ-PWT-LAU0: launch configuration shall be calibratable. */
typedef struct {
    uint16_t launch_rpm;
    uint16_t slip_target;
    uint16_t trim_offset;
    uint16_t limp_factor;
} Pwt_Launch_Config_t;

/* REQ-PWT-LAU1: launch runtime state shall be observable. */
typedef struct {
    uint8_t   phase;         /* current launch phase */
    uint16_t  value;         /* primary processed value */
    uint16_t  raw;           /* last raw sample */
    uint8_t   valid;         /* 1 = signal path healthy */
    uint16_t  fault_count;   /* accumulated fault counter (added R2.0) */
    uint32_t  uptime_ticks;  /* ticks since init (added R4.0) */
    int16_t   trim;          /* applied trim offset (added R4.0) */
} Pwt_Launch_State_t;

void Pwt_Launch_Init(const Pwt_Launch_Config_t *cfg);
uint16_t Pwt_Launch_GetLaunchRpm(void);
void Pwt_Launch_SetLaunchRpm(uint16_t v, uint8_t ramp);
uint16_t Pwt_Launch_GetSlipTarget(void);
void Pwt_Launch_SetSlipTarget(uint16_t v);
uint16_t Pwt_Launch_GetTrimOffset(void);
void Pwt_Launch_SetTrimOffset(uint16_t v);
uint16_t Pwt_Launch_GetLimpFactor(void);
void Pwt_Launch_SetLimpFactor(uint16_t v);
uint16_t Pwt_Launch_ReadClutchPos(void);
uint16_t Pwt_Launch_ReadTraction(void);
uint16_t Pwt_Launch_ReadAux01(void);
uint16_t Pwt_Launch_ReadAux02(void);
uint16_t Pwt_Launch_ReadAux03(void);
uint16_t Pwt_Launch_ReadAux04(void);
uint16_t Pwt_Launch_Compute(void);
uint8_t Pwt_Launch_SelfTest(void);
void Pwt_Launch_Step(void);
const Pwt_Launch_State_t *Pwt_Launch_GetState(void);

#endif /* VCU_PWT_LAUNCH_H */
