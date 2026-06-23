#ifndef VCU_COM_LINMASTER_H
#define VCU_COM_LINMASTER_H

#include <stdint.h>

/* CommGateway :: linmaster module (release R3.0)
 * Communication Gateway: CAN/LIN routing, signal mapping and bus monitoring. */

typedef enum {
    COM_LINMASTER_P_OFF = 0,
    COM_LINMASTER_P_INIT,
    COM_LINMASTER_P_RUN,
    COM_LINMASTER_P_FAULT,
    COM_LINMASTER_P_LIMP
} Com_Linmaster_Phase_t;

/* REQ-COM-LIN0: linmaster configuration shall be calibratable. */
typedef struct {
    uint16_t schedule_ms;
    uint16_t break_bits;
    uint16_t trim_offset;
} Com_Linmaster_Config_t;

/* REQ-COM-LIN1: linmaster runtime state shall be observable. */
typedef struct {
    uint8_t   phase;         /* current linmaster phase */
    uint16_t  value;         /* primary processed value */
    uint16_t  raw;           /* last raw sample */
    uint8_t   valid;         /* 1 = signal path healthy */
    uint16_t  fault_count;   /* accumulated fault counter (added R2.0) */
} Com_Linmaster_State_t;

void Com_Linmaster_Init(const Com_Linmaster_Config_t *cfg);
uint16_t Com_Linmaster_GetScheduleMs(void);
void Com_Linmaster_SetScheduleMs(uint16_t v);
uint16_t Com_Linmaster_GetBreakBits(void);
void Com_Linmaster_SetBreakBits(uint16_t v);
uint16_t Com_Linmaster_GetTrimOffset(void);
void Com_Linmaster_SetTrimOffset(uint16_t v);
uint16_t Com_Linmaster_ReadLinPid(void);
uint16_t Com_Linmaster_ReadLinErr(void);
uint16_t Com_Linmaster_ReadAux01(void);
uint16_t Com_Linmaster_ReadAux02(void);
uint16_t Com_Linmaster_Compute(void);
uint8_t Com_Linmaster_SelfTest(void);
void Com_Linmaster_Step(void);
const Com_Linmaster_State_t *Com_Linmaster_GetState(void);

#endif /* VCU_COM_LINMASTER_H */
