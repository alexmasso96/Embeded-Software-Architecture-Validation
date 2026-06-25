#ifndef VCU_BCM_WIPERS_H
#define VCU_BCM_WIPERS_H

#include <stdint.h>

/* BodyControl :: wipers module (release R2.0)
 * Body Control Module: exterior/interior lighting, doors, wipers, windows and mirrors. */

typedef enum {
    BCM_WIPERS_P_OFF = 0,
    BCM_WIPERS_P_INIT,
    BCM_WIPERS_P_RUN,
    BCM_WIPERS_P_FAULT,
    BCM_WIPERS_P_LIMP
} Bcm_Wipers_Phase_t;

/* REQ-BCM-WIP0: wipers configuration shall be calibratable. */
typedef struct {
    uint16_t interval_ms;
    uint16_t park_offset_deg;
    uint16_t speed_high;
} Bcm_Wipers_Config_t;

/* REQ-BCM-WIP1: wipers runtime state shall be observable. */
typedef struct {
    uint8_t   phase;         /* current wipers phase */
    uint16_t  value;         /* primary processed value */
    uint16_t  raw;           /* last raw sample */
    uint8_t   valid;         /* 1 = signal path healthy */
    uint16_t  fault_count;   /* accumulated fault counter (added R2.0) */
} Bcm_Wipers_State_t;

void Bcm_Wipers_Init(const Bcm_Wipers_Config_t *cfg);
uint16_t Bcm_Wipers_GetIntervalMs(void);
void Bcm_Wipers_SetIntervalMs(uint16_t v);
uint16_t Bcm_Wipers_GetParkOffsetDeg(void);
void Bcm_Wipers_SetParkOffsetDeg(uint16_t v);
uint16_t Bcm_Wipers_GetSpeedHigh(void);
void Bcm_Wipers_SetSpeedHigh(uint16_t v);
uint16_t Bcm_Wipers_ReadRainLevel(void);
uint16_t Bcm_Wipers_ReadParkSwitch(void);
uint16_t Bcm_Wipers_ReadMotorLoad(void);
uint16_t Bcm_Wipers_ReadAux01(void);
uint16_t Bcm_Wipers_Compute(void);
void Bcm_Wipers_Step(void);
const Bcm_Wipers_State_t *Bcm_Wipers_GetState(void);

#endif /* VCU_BCM_WIPERS_H */
