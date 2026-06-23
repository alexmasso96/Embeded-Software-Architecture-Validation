#ifndef VCU_COM_CANROUTER_H
#define VCU_COM_CANROUTER_H

#include <stdint.h>

/* CommGateway :: canrouter module (release R1.0)
 * Communication Gateway: CAN/LIN routing, signal mapping and bus monitoring. */

typedef enum {
    COM_CANROUTER_P_OFF = 0,
    COM_CANROUTER_P_INIT,
    COM_CANROUTER_P_RUN,
    COM_CANROUTER_P_FAULT,
    COM_CANROUTER_P_LIMP
} Com_Canrouter_Phase_t;

/* REQ-COM-CAN0: canrouter configuration shall be calibratable. */
typedef struct {
    uint16_t bus_load_limit;
    uint16_t route_table_len;
} Com_Canrouter_Config_t;

/* REQ-COM-CAN1: canrouter runtime state shall be observable. */
typedef struct {
    uint8_t   phase;         /* current canrouter phase */
    uint16_t  value;         /* primary processed value */
    uint16_t  raw;           /* last raw sample */
    uint8_t   valid;         /* 1 = signal path healthy */
} Com_Canrouter_State_t;

void Com_Canrouter_Init(const Com_Canrouter_Config_t *cfg);
uint16_t Com_Canrouter_GetBusLoadLimit(void);
void Com_Canrouter_SetBusLoadLimit(uint16_t v);
uint16_t Com_Canrouter_GetRouteTableLen(void);
void Com_Canrouter_SetRouteTableLen(uint16_t v);
uint16_t Com_Canrouter_ReadRxId(void);
uint16_t Com_Canrouter_ReadRxDlc(void);
uint16_t Com_Canrouter_ReadBusOff(void);
uint16_t Com_Canrouter_Compute(void);
void Com_Canrouter_LegacyReset(void);
void Com_Canrouter_Step(void);
const Com_Canrouter_State_t *Com_Canrouter_GetState(void);

#endif /* VCU_COM_CANROUTER_H */
