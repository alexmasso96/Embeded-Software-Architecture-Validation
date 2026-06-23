#ifndef VCU_COM_NETMON_H
#define VCU_COM_NETMON_H

#include <stdint.h>

/* CommGateway :: netmon module (release R5.0)
 * Communication Gateway: CAN/LIN routing, signal mapping and bus monitoring. */

typedef enum {
    COM_NETMON_P_OFF = 0,
    COM_NETMON_P_INIT,
    COM_NETMON_P_RUN,
    COM_NETMON_P_FAULT,
    COM_NETMON_P_LIMP
} Com_Netmon_Phase_t;

/* REQ-COM-NET0: netmon configuration shall be calibratable. */
typedef struct {
    uint16_t wake_timeout_ms;
    uint16_t sleep_delay_ms;
    uint16_t trim_offset;
    uint16_t limp_factor;
} Com_Netmon_Config_t;

/* REQ-COM-NET1: netmon runtime state shall be observable. */
typedef struct {
    uint8_t   phase;         /* current netmon phase */
    uint16_t  value;         /* primary processed value */
    uint16_t  raw;           /* last raw sample */
    uint8_t   valid;         /* 1 = signal path healthy */
    uint16_t  fault_count;   /* accumulated fault counter (added R2.0) */
    uint32_t  uptime_ticks;  /* ticks since init (added R4.0) */
    int16_t   trim;          /* applied trim offset (added R4.0) */
} Com_Netmon_State_t;

void Com_Netmon_Init(const Com_Netmon_Config_t *cfg);
uint16_t Com_Netmon_GetWakeTimeoutMs(void);
void Com_Netmon_SetWakeTimeoutMs(uint16_t v, uint8_t ramp);
uint16_t Com_Netmon_GetSleepDelayMs(void);
void Com_Netmon_SetSleepDelayMs(uint16_t v);
uint16_t Com_Netmon_GetTrimOffset(void);
void Com_Netmon_SetTrimOffset(uint16_t v);
uint16_t Com_Netmon_GetLimpFactor(void);
void Com_Netmon_SetLimpFactor(uint16_t v);
uint16_t Com_Netmon_ReadBusActivity(void);
uint16_t Com_Netmon_ReadWakeLine(void);
uint16_t Com_Netmon_ReadAux01(void);
uint16_t Com_Netmon_ReadAux02(void);
uint16_t Com_Netmon_ReadAux03(void);
uint16_t Com_Netmon_ReadAux04(void);
uint16_t Com_Netmon_Compute(void);
uint8_t Com_Netmon_SelfTest(void);
void Com_Netmon_Step(void);
const Com_Netmon_State_t *Com_Netmon_GetState(void);

#endif /* VCU_COM_NETMON_H */
