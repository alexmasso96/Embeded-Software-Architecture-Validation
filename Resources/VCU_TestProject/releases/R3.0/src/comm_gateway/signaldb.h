#ifndef VCU_COM_SIGNALDB_H
#define VCU_COM_SIGNALDB_H

#include <stdint.h>

/* CommGateway :: signaldb module (release R3.0)
 * Communication Gateway: CAN/LIN routing, signal mapping and bus monitoring. */

typedef enum {
    COM_SIGNALDB_P_OFF = 0,
    COM_SIGNALDB_P_INIT,
    COM_SIGNALDB_P_RUN,
    COM_SIGNALDB_P_FAULT,
    COM_SIGNALDB_P_LIMP
} Com_Signaldb_Phase_t;

/* REQ-COM-SIG0: signaldb configuration shall be calibratable. */
typedef struct {
    uint16_t timeout_ms;
    uint16_t default_value;
    uint16_t trim_offset;
} Com_Signaldb_Config_t;

/* REQ-COM-SIG1: signaldb runtime state shall be observable. */
typedef struct {
    uint8_t   phase;         /* current signaldb phase */
    uint16_t  value;         /* primary processed value */
    uint16_t  raw;           /* last raw sample */
    uint8_t   valid;         /* 1 = signal path healthy */
    uint16_t  fault_count;   /* accumulated fault counter (added R2.0) */
} Com_Signaldb_State_t;

void Com_Signaldb_Init(const Com_Signaldb_Config_t *cfg);
uint16_t Com_Signaldb_GetTimeoutMs(void);
void Com_Signaldb_SetTimeoutMs(uint16_t v);
uint16_t Com_Signaldb_GetDefaultValue(void);
void Com_Signaldb_SetDefaultValue(uint16_t v);
uint16_t Com_Signaldb_GetTrimOffset(void);
void Com_Signaldb_SetTrimOffset(uint16_t v);
uint16_t Com_Signaldb_ReadRawA(void);
uint16_t Com_Signaldb_ReadRawB(void);
uint16_t Com_Signaldb_ReadRawC(void);
uint16_t Com_Signaldb_ReadAux01(void);
uint16_t Com_Signaldb_ReadAux02(void);
uint16_t Com_Signaldb_Compute(void);
uint8_t Com_Signaldb_SelfTest(void);
void Com_Signaldb_Step(void);
const Com_Signaldb_State_t *Com_Signaldb_GetState(void);

#endif /* VCU_COM_SIGNALDB_H */
