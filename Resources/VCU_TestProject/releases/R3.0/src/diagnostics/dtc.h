#ifndef VCU_DIAG_DTC_H
#define VCU_DIAG_DTC_H

#include <stdint.h>

/* Diagnostics :: dtc module (release R3.0)
 * Diagnostics: DTC management, freeze frames, UDS services and monitors. */

typedef enum {
    DIAG_DTC_P_OFF = 0,
    DIAG_DTC_P_INIT,
    DIAG_DTC_P_RUN,
    DIAG_DTC_P_FAULT,
    DIAG_DTC_P_LIMP
} Diag_Dtc_Phase_t;

/* REQ-DIAG-DTC0: dtc configuration shall be calibratable. */
typedef struct {
    uint16_t aging_threshold;
    uint16_t confirm_cycles;
    uint16_t trim_offset;
} Diag_Dtc_Config_t;

/* REQ-DIAG-DTC1: dtc runtime state shall be observable. */
typedef struct {
    uint8_t   phase;         /* current dtc phase */
    uint16_t  value;         /* primary processed value */
    uint16_t  raw;           /* last raw sample */
    uint8_t   valid;         /* 1 = signal path healthy */
    uint16_t  fault_count;   /* accumulated fault counter (added R2.0) */
} Diag_Dtc_State_t;

void Diag_Dtc_Init(const Diag_Dtc_Config_t *cfg);
uint16_t Diag_Dtc_GetAgingThreshold(void);
void Diag_Dtc_SetAgingThreshold(uint16_t v);
uint16_t Diag_Dtc_GetConfirmCycles(void);
void Diag_Dtc_SetConfirmCycles(uint16_t v);
uint16_t Diag_Dtc_GetTrimOffset(void);
void Diag_Dtc_SetTrimOffset(uint16_t v);
uint16_t Diag_Dtc_ReadFaultBits(void);
uint16_t Diag_Dtc_ReadIgnCycle(void);
uint16_t Diag_Dtc_ReadAux01(void);
uint16_t Diag_Dtc_ReadAux02(void);
uint16_t Diag_Dtc_Compute(void);
uint8_t Diag_Dtc_SelfTest(void);
void Diag_Dtc_Step(void);
const Diag_Dtc_State_t *Diag_Dtc_GetState(void);

#endif /* VCU_DIAG_DTC_H */
