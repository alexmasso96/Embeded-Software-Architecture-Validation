#ifndef VCU_BCM_AMBIENT_H
#define VCU_BCM_AMBIENT_H

#include <stdint.h>

/* BodyControl :: ambient module (release R4.0)
 * Body Control Module: exterior/interior lighting, doors, wipers, windows and mirrors. */

typedef enum {
    BCM_AMBIENT_P_OFF = 0,
    BCM_AMBIENT_P_INIT,
    BCM_AMBIENT_P_RUN,
    BCM_AMBIENT_P_FAULT,
    BCM_AMBIENT_P_LIMP
} Bcm_Ambient_Phase_t;

/* REQ-BCM-AMB0: ambient configuration shall be calibratable. */
typedef struct {
    uint16_t brightness;
    uint16_t color_temp;
    uint16_t trim_offset;
} Bcm_Ambient_Config_t;

/* REQ-BCM-AMB1: ambient runtime state shall be observable. */
typedef struct {
    uint8_t   phase;         /* current ambient phase */
    uint16_t  value;         /* primary processed value */
    uint16_t  raw;           /* last raw sample */
    uint8_t   valid;         /* 1 = signal path healthy */
    uint16_t  fault_count;   /* accumulated fault counter (added R2.0) */
    uint32_t  uptime_ticks;  /* ticks since init (added R4.0) */
    int16_t   trim;          /* applied trim offset (added R4.0) */
} Bcm_Ambient_State_t;

void Bcm_Ambient_Init(const Bcm_Ambient_Config_t *cfg);
uint16_t Bcm_Ambient_GetBrightness(void);
void Bcm_Ambient_SetBrightness(uint16_t v, uint8_t ramp);
uint16_t Bcm_Ambient_GetColorTemp(void);
void Bcm_Ambient_SetColorTemp(uint16_t v);
uint16_t Bcm_Ambient_GetTrimOffset(void);
void Bcm_Ambient_SetTrimOffset(uint16_t v);
uint16_t Bcm_Ambient_ReadDoorOpen(void);
uint16_t Bcm_Ambient_ReadDimmer(void);
uint16_t Bcm_Ambient_ReadAux01(void);
uint16_t Bcm_Ambient_ReadAux02(void);
uint16_t Bcm_Ambient_ReadAux03(void);
uint16_t Bcm_Ambient_Compute(void);
uint8_t Bcm_Ambient_SelfTest(void);
void Bcm_Ambient_Step(void);
const Bcm_Ambient_State_t *Bcm_Ambient_GetState(void);

#endif /* VCU_BCM_AMBIENT_H */
