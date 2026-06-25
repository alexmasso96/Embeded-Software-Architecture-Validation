#ifndef VCU_DIAG_FREEZEFRAME_H
#define VCU_DIAG_FREEZEFRAME_H

#include <stdint.h>

/* Diagnostics :: freezeframe module (release R3.0)
 * Diagnostics: DTC management, freeze frames, UDS services and monitors. */

typedef enum {
    DIAG_FREEZEFRAME_P_OFF = 0,
    DIAG_FREEZEFRAME_P_INIT,
    DIAG_FREEZEFRAME_P_RUN,
    DIAG_FREEZEFRAME_P_FAULT,
    DIAG_FREEZEFRAME_P_LIMP
} Diag_Freezeframe_Phase_t;

/* REQ-DIAG-FRE0: freezeframe configuration shall be calibratable. */
typedef struct {
    uint16_t frame_depth;
    uint16_t snapshot_mask;
    uint16_t trim_offset;
} Diag_Freezeframe_Config_t;

/* REQ-DIAG-FRE1: freezeframe runtime state shall be observable. */
typedef struct {
    uint8_t   phase;         /* current freezeframe phase */
    uint16_t  value;         /* primary processed value */
    uint16_t  raw;           /* last raw sample */
    uint8_t   valid;         /* 1 = signal path healthy */
    uint16_t  fault_count;   /* accumulated fault counter (added R2.0) */
} Diag_Freezeframe_State_t;

void Diag_Freezeframe_Init(const Diag_Freezeframe_Config_t *cfg);
uint16_t Diag_Freezeframe_GetFrameDepth(void);
void Diag_Freezeframe_SetFrameDepth(uint16_t v);
uint16_t Diag_Freezeframe_GetSnapshotMask(void);
void Diag_Freezeframe_SetSnapshotMask(uint16_t v);
uint16_t Diag_Freezeframe_GetTrimOffset(void);
void Diag_Freezeframe_SetTrimOffset(uint16_t v);
uint16_t Diag_Freezeframe_ReadRpmSnap(void);
uint16_t Diag_Freezeframe_ReadSpeedSnap(void);
uint16_t Diag_Freezeframe_ReadAux01(void);
uint16_t Diag_Freezeframe_ReadAux02(void);
uint16_t Diag_Freezeframe_Compute(void);
uint8_t Diag_Freezeframe_SelfTest(void);
void Diag_Freezeframe_Step(void);
const Diag_Freezeframe_State_t *Diag_Freezeframe_GetState(void);

#endif /* VCU_DIAG_FREEZEFRAME_H */
