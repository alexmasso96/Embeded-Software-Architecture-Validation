#ifndef VCU_DIAG_SECURITY_H
#define VCU_DIAG_SECURITY_H

#include <stdint.h>

/* Diagnostics :: security module (release R4.0)
 * Diagnostics: DTC management, freeze frames, UDS services and monitors. */

typedef enum {
    DIAG_SECURITY_P_OFF = 0,
    DIAG_SECURITY_P_INIT,
    DIAG_SECURITY_P_RUN,
    DIAG_SECURITY_P_FAULT,
    DIAG_SECURITY_P_LIMP
} Diag_Security_Phase_t;

/* REQ-DIAG-SEC0: security configuration shall be calibratable. */
typedef struct {
    uint16_t seed_mask;
    uint16_t delay_ms;
    uint16_t trim_offset;
} Diag_Security_Config_t;

/* REQ-DIAG-SEC1: security runtime state shall be observable. */
typedef struct {
    uint8_t   phase;         /* current security phase */
    uint16_t  value;         /* primary processed value */
    uint16_t  raw;           /* last raw sample */
    uint8_t   valid;         /* 1 = signal path healthy */
    uint16_t  fault_count;   /* accumulated fault counter (added R2.0) */
    uint32_t  uptime_ticks;  /* ticks since init (added R4.0) */
    int16_t   trim;          /* applied trim offset (added R4.0) */
} Diag_Security_State_t;

void Diag_Security_Init(const Diag_Security_Config_t *cfg);
uint16_t Diag_Security_GetSeedMask(void);
void Diag_Security_SetSeedMask(uint16_t v, uint8_t ramp);
uint16_t Diag_Security_GetDelayMs(void);
void Diag_Security_SetDelayMs(uint16_t v);
uint16_t Diag_Security_GetTrimOffset(void);
void Diag_Security_SetTrimOffset(uint16_t v);
uint16_t Diag_Security_ReadAttemptCount(void);
uint16_t Diag_Security_ReadUnlocked(void);
uint16_t Diag_Security_ReadAux01(void);
uint16_t Diag_Security_ReadAux02(void);
uint16_t Diag_Security_ReadAux03(void);
uint16_t Diag_Security_Compute(void);
uint8_t Diag_Security_SelfTest(void);
void Diag_Security_Step(void);
const Diag_Security_State_t *Diag_Security_GetState(void);

#endif /* VCU_DIAG_SECURITY_H */
