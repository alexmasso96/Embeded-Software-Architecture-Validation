#ifndef VCU_DIAG_MONITOR_H
#define VCU_DIAG_MONITOR_H

#include <stdint.h>

/* Diagnostics :: monitor module (release R3.0)
 * Diagnostics: DTC management, freeze frames, UDS services and monitors. */

typedef enum {
    DIAG_MONITOR_P_OFF = 0,
    DIAG_MONITOR_P_INIT,
    DIAG_MONITOR_P_RUN,
    DIAG_MONITOR_P_FAULT,
    DIAG_MONITOR_P_LIMP
} Diag_Monitor_Phase_t;

/* REQ-DIAG-MON0: monitor configuration shall be calibratable. */
typedef struct {
    uint16_t misfire_thresh;
    uint16_t cat_temp_limit;
    uint16_t trim_offset;
} Diag_Monitor_Config_t;

/* REQ-DIAG-MON1: monitor runtime state shall be observable. */
typedef struct {
    uint8_t   phase;         /* current monitor phase */
    uint16_t  value;         /* primary processed value */
    uint16_t  raw;           /* last raw sample */
    uint8_t   valid;         /* 1 = signal path healthy */
    uint16_t  fault_count;   /* accumulated fault counter (added R2.0) */
} Diag_Monitor_State_t;

void Diag_Monitor_Init(const Diag_Monitor_Config_t *cfg);
uint16_t Diag_Monitor_GetMisfireThresh(void);
void Diag_Monitor_SetMisfireThresh(uint16_t v);
uint16_t Diag_Monitor_GetCatTempLimit(void);
void Diag_Monitor_SetCatTempLimit(uint16_t v);
uint16_t Diag_Monitor_GetTrimOffset(void);
void Diag_Monitor_SetTrimOffset(uint16_t v);
uint16_t Diag_Monitor_ReadO2Sensor(void);
uint16_t Diag_Monitor_ReadMisfireCount(void);
uint16_t Diag_Monitor_ReadAux01(void);
uint16_t Diag_Monitor_ReadAux02(void);
uint16_t Diag_Monitor_Compute(void);
uint8_t Diag_Monitor_SelfTest(void);
void Diag_Monitor_Step(void);
const Diag_Monitor_State_t *Diag_Monitor_GetState(void);

#endif /* VCU_DIAG_MONITOR_H */
