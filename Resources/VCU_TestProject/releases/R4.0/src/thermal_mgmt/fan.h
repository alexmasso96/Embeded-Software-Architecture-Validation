#ifndef VCU_THM_FAN_H
#define VCU_THM_FAN_H

#include <stdint.h>

/* ThermalMgmt :: fan module (release R4.0)
 * Thermal Management: coolant loops, HVAC, pump and fan control. */

typedef enum {
    THM_FAN_P_OFF = 0,
    THM_FAN_P_INIT,
    THM_FAN_P_RUN,
    THM_FAN_P_FAULT,
    THM_FAN_P_LIMP
} Thm_Fan_Phase_t;

/* REQ-THM-FAN0: fan configuration shall be calibratable. */
typedef struct {
    uint16_t on_thresh_c;
    uint16_t off_thresh_c;
    uint16_t trim_offset;
} Thm_Fan_Config_t;

/* REQ-THM-FAN1: fan runtime state shall be observable. */
typedef struct {
    uint8_t   phase;         /* current fan phase */
    uint16_t  value;         /* primary processed value */
    uint16_t  raw;           /* last raw sample */
    uint8_t   valid;         /* 1 = signal path healthy */
    uint16_t  fault_count;   /* accumulated fault counter (added R2.0) */
    uint32_t  uptime_ticks;  /* ticks since init (added R4.0) */
    int16_t   trim;          /* applied trim offset (added R4.0) */
} Thm_Fan_State_t;

void Thm_Fan_Init(const Thm_Fan_Config_t *cfg);
uint16_t Thm_Fan_GetOnThreshC(void);
void Thm_Fan_SetOnThreshC(uint16_t v, uint8_t ramp);
uint16_t Thm_Fan_GetOffThreshC(void);
void Thm_Fan_SetOffThreshC(uint16_t v);
uint16_t Thm_Fan_GetTrimOffset(void);
void Thm_Fan_SetTrimOffset(uint16_t v);
uint16_t Thm_Fan_ReadRadiatorC(void);
uint16_t Thm_Fan_ReadFanRpm(void);
uint16_t Thm_Fan_ReadAux01(void);
uint16_t Thm_Fan_ReadAux02(void);
uint16_t Thm_Fan_ReadAux03(void);
uint16_t Thm_Fan_Compute(void);
uint8_t Thm_Fan_SelfTest(void);
void Thm_Fan_Step(void);
const Thm_Fan_State_t *Thm_Fan_GetState(void);

#endif /* VCU_THM_FAN_H */
