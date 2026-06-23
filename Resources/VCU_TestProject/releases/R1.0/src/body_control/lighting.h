#ifndef VCU_BCM_LIGHTING_H
#define VCU_BCM_LIGHTING_H

#include <stdint.h>

/* BodyControl :: lighting module (release R1.0)
 * Body Control Module: exterior/interior lighting, doors, wipers, windows and mirrors. */

typedef enum {
    BCM_LIGHTING_P_OFF = 0,
    BCM_LIGHTING_P_INIT,
    BCM_LIGHTING_P_RUN,
    BCM_LIGHTING_P_FAULT,
    BCM_LIGHTING_P_LIMP
} Bcm_Lighting_Phase_t;

/* REQ-BCM-LIG0: lighting configuration shall be calibratable. */
typedef struct {
    uint16_t max_current_ma;
    uint16_t dim_rate_pct_s;
    uint16_t fade_ms;
} Bcm_Lighting_Config_t;

/* REQ-BCM-LIG1: lighting runtime state shall be observable. */
typedef struct {
    uint8_t   phase;         /* current lighting phase */
    uint16_t  value;         /* primary processed value */
    uint16_t  raw;           /* last raw sample */
    uint8_t   valid;         /* 1 = signal path healthy */
} Bcm_Lighting_State_t;

void Bcm_Lighting_Init(const Bcm_Lighting_Config_t *cfg);
uint16_t Bcm_Lighting_GetMaxCurrentMa(void);
void Bcm_Lighting_SetMaxCurrentMa(uint16_t v);
uint16_t Bcm_Lighting_GetDimRatePctS(void);
void Bcm_Lighting_SetDimRatePctS(uint16_t v);
uint16_t Bcm_Lighting_GetFadeMs(void);
void Bcm_Lighting_SetFadeMs(uint16_t v);
uint16_t Bcm_Lighting_ReadSwitch(void);
uint16_t Bcm_Lighting_ReadBusVoltage(void);
uint16_t Bcm_Lighting_ReadAmbientLux(void);
uint16_t Bcm_Lighting_Compute(void);
void Bcm_Lighting_LegacyReset(void);
void Bcm_Lighting_Step(void);
const Bcm_Lighting_State_t *Bcm_Lighting_GetState(void);

#endif /* VCU_BCM_LIGHTING_H */
