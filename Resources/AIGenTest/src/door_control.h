#ifndef DOOR_CONTROL_H
#define DOOR_CONTROL_H

#include <stdint.h>

/* Lock states reported by the door control module. */
#define DOOR_STATE_UNLOCKED   0u
#define DOOR_STATE_LOCKED     1u
#define DOOR_STATE_FAULT      2u

/* Voltage threshold (in mV) below which locking is inhibited. */
#define DOOR_LOCK_MIN_VOLTAGE 9000u

/* Initialise the door control module. Called once at ECU startup. */
void DoorControl_Init(void);

/* Cyclic 10ms task: samples the door switch and updates the lock state. */
void DoorControl_10ms(void);

/* Returns the current lock state (DOOR_STATE_*). */
uint8_t DoorControl_GetLockState(void);

#endif /* DOOR_CONTROL_H */
