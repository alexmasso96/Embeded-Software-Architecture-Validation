#ifndef VCU_CHG_SEQUENCER_H
#define VCU_CHG_SEQUENCER_H

#include <stdint.h>

/* ChargingCtrl :: sequencer module (release R5.0)
 * Charging Control (introduced R3.0): AC/DC charging state machine, control pilot and metering. */

typedef enum {
    CHG_SEQUENCER_P_OFF = 0,
    CHG_SEQUENCER_P_INIT,
    CHG_SEQUENCER_P_RUN,
    CHG_SEQUENCER_P_FAULT,
    CHG_SEQUENCER_P_LIMP
} Chg_Sequencer_Phase_t;

/* REQ-CHG-SEQ0: sequencer configuration shall be calibratable. */
typedef struct {
    uint16_t state_timeout_ms;
    uint16_t retry_limit;
    uint16_t trim_offset;
    uint16_t limp_factor;
} Chg_Sequencer_Config_t;

/* REQ-CHG-SEQ1: sequencer runtime state shall be observable. */
typedef struct {
    uint8_t   phase;         /* current sequencer phase */
    uint16_t  value;         /* primary processed value */
    uint16_t  raw;           /* last raw sample */
    uint8_t   valid;         /* 1 = signal path healthy */
    uint16_t  fault_count;   /* accumulated fault counter (added R2.0) */
    uint32_t  uptime_ticks;  /* ticks since init (added R4.0) */
    int16_t   trim;          /* applied trim offset (added R4.0) */
} Chg_Sequencer_State_t;

void Chg_Sequencer_Init(const Chg_Sequencer_Config_t *cfg);
uint16_t Chg_Sequencer_GetStateTimeoutMs(void);
void Chg_Sequencer_SetStateTimeoutMs(uint16_t v, uint8_t ramp);
uint16_t Chg_Sequencer_GetRetryLimit(void);
void Chg_Sequencer_SetRetryLimit(uint16_t v);
uint16_t Chg_Sequencer_GetTrimOffset(void);
void Chg_Sequencer_SetTrimOffset(uint16_t v);
uint16_t Chg_Sequencer_GetLimpFactor(void);
void Chg_Sequencer_SetLimpFactor(uint16_t v);
uint16_t Chg_Sequencer_ReadContactorAux(void);
uint16_t Chg_Sequencer_ReadInsulationMohm(void);
uint16_t Chg_Sequencer_ReadAux01(void);
uint16_t Chg_Sequencer_ReadAux02(void);
uint16_t Chg_Sequencer_ReadAux03(void);
uint16_t Chg_Sequencer_ReadAux04(void);
uint16_t Chg_Sequencer_Compute(void);
uint8_t Chg_Sequencer_SelfTest(void);
void Chg_Sequencer_Step(void);
const Chg_Sequencer_State_t *Chg_Sequencer_GetState(void);

#endif /* VCU_CHG_SEQUENCER_H */
