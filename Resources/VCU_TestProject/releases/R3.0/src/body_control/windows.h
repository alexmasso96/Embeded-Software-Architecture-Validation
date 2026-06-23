#ifndef VCU_BCM_WINDOWS_H
#define VCU_BCM_WINDOWS_H

#include <stdint.h>

/* BodyControl :: windows module (release R3.0)
 * Body Control Module: exterior/interior lighting, doors, wipers, windows and mirrors. */

typedef enum {
    BCM_WINDOWS_P_OFF = 0,
    BCM_WINDOWS_P_INIT,
    BCM_WINDOWS_P_RUN,
    BCM_WINDOWS_P_FAULT,
    BCM_WINDOWS_P_LIMP
} Bcm_Windows_Phase_t;

/* REQ-BCM-WIN0: windows configuration shall be calibratable. */
typedef struct {
    uint16_t max_duty;
    uint16_t pinch_thresh_ma;
    uint16_t auto_stop_mm;
    uint16_t trim_offset;
} Bcm_Windows_Config_t;

/* REQ-BCM-WIN1: windows runtime state shall be observable. */
typedef struct {
    uint8_t   phase;         /* current windows phase */
    uint16_t  value;         /* primary processed value */
    uint16_t  raw;           /* last raw sample */
    uint8_t   valid;         /* 1 = signal path healthy */
    uint16_t  fault_count;   /* accumulated fault counter (added R2.0) */
} Bcm_Windows_State_t;

void Bcm_Windows_Init(const Bcm_Windows_Config_t *cfg);
uint16_t Bcm_Windows_GetMaxDuty(void);
void Bcm_Windows_SetMaxDuty(uint16_t v);
uint16_t Bcm_Windows_GetPinchThreshMa(void);
void Bcm_Windows_SetPinchThreshMa(uint16_t v);
uint16_t Bcm_Windows_GetAutoStopMm(void);
void Bcm_Windows_SetAutoStopMm(uint16_t v);
uint16_t Bcm_Windows_GetTrimOffset(void);
void Bcm_Windows_SetTrimOffset(uint16_t v);
uint16_t Bcm_Windows_ReadHallPos(void);
uint16_t Bcm_Windows_ReadCurrent(void);
uint16_t Bcm_Windows_ReadUpBtn(void);
uint16_t Bcm_Windows_ReadDownBtn(void);
uint16_t Bcm_Windows_ReadAux01(void);
uint16_t Bcm_Windows_ReadAux02(void);
uint16_t Bcm_Windows_Compute(void);
uint8_t Bcm_Windows_SelfTest(void);
void Bcm_Windows_Step(void);
const Bcm_Windows_State_t *Bcm_Windows_GetState(void);

#endif /* VCU_BCM_WINDOWS_H */
