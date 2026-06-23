#ifndef VCU_BCM_DOORS_H
#define VCU_BCM_DOORS_H

#include <stdint.h>

/* BodyControl :: doors module (release R1.0)
 * Body Control Module: exterior/interior lighting, doors, wipers, windows and mirrors. */

typedef enum {
    BCM_DOORS_P_OFF = 0,
    BCM_DOORS_P_INIT,
    BCM_DOORS_P_RUN,
    BCM_DOORS_P_FAULT,
    BCM_DOORS_P_LIMP
} Bcm_Doors_Phase_t;

/* REQ-BCM-DOO0: doors configuration shall be calibratable. */
typedef struct {
    uint16_t lock_timeout_ms;
    uint16_t ajar_debounce;
} Bcm_Doors_Config_t;

/* REQ-BCM-DOO1: doors runtime state shall be observable. */
typedef struct {
    uint8_t   phase;         /* current doors phase */
    uint16_t  value;         /* primary processed value */
    uint16_t  raw;           /* last raw sample */
    uint8_t   valid;         /* 1 = signal path healthy */
} Bcm_Doors_State_t;

void Bcm_Doors_Init(const Bcm_Doors_Config_t *cfg);
uint16_t Bcm_Doors_GetLockTimeoutMs(void);
void Bcm_Doors_SetLockTimeoutMs(uint16_t v);
uint16_t Bcm_Doors_GetAjarDebounce(void);
void Bcm_Doors_SetAjarDebounce(uint16_t v);
uint16_t Bcm_Doors_ReadLatchState(void);
uint16_t Bcm_Doors_ReadHandlePull(void);
uint16_t Bcm_Doors_ReadLockBtn(void);
uint16_t Bcm_Doors_Compute(void);
void Bcm_Doors_LegacyReset(void);
void Bcm_Doors_Step(void);
const Bcm_Doors_State_t *Bcm_Doors_GetState(void);

#endif /* VCU_BCM_DOORS_H */
