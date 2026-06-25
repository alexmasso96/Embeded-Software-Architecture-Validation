#ifndef VCU_DIAG_UDS_H
#define VCU_DIAG_UDS_H

#include <stdint.h>

/* Diagnostics :: uds module (release R3.0)
 * Diagnostics: DTC management, freeze frames, UDS services and monitors. */

typedef enum {
    DIAG_UDS_P_OFF = 0,
    DIAG_UDS_P_INIT,
    DIAG_UDS_P_RUN,
    DIAG_UDS_P_FAULT,
    DIAG_UDS_P_LIMP
} Diag_Uds_Phase_t;

/* REQ-DIAG-UDS0: uds configuration shall be calibratable. */
typedef struct {
    uint16_t p2_timeout_ms;
    uint16_t s3_timeout_ms;
    uint16_t trim_offset;
} Diag_Uds_Config_t;

/* REQ-DIAG-UDS1: uds runtime state shall be observable. */
typedef struct {
    uint8_t   phase;         /* current uds phase */
    uint16_t  value;         /* primary processed value */
    uint16_t  raw;           /* last raw sample */
    uint8_t   valid;         /* 1 = signal path healthy */
    uint16_t  fault_count;   /* accumulated fault counter (added R2.0) */
} Diag_Uds_State_t;

void Diag_Uds_Init(const Diag_Uds_Config_t *cfg);
uint16_t Diag_Uds_GetP2TimeoutMs(void);
void Diag_Uds_SetP2TimeoutMs(uint16_t v);
uint16_t Diag_Uds_GetS3TimeoutMs(void);
void Diag_Uds_SetS3TimeoutMs(uint16_t v);
uint16_t Diag_Uds_GetTrimOffset(void);
void Diag_Uds_SetTrimOffset(uint16_t v);
uint16_t Diag_Uds_ReadRxPending(void);
uint16_t Diag_Uds_ReadSessionType(void);
uint16_t Diag_Uds_ReadAux01(void);
uint16_t Diag_Uds_ReadAux02(void);
uint16_t Diag_Uds_Compute(void);
uint8_t Diag_Uds_SelfTest(void);
void Diag_Uds_Step(void);
const Diag_Uds_State_t *Diag_Uds_GetState(void);

#endif /* VCU_DIAG_UDS_H */
