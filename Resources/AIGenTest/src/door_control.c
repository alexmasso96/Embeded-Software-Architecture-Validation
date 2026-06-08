#include "door_control.h"

/* Module-private state. */
static uint8_t  doorLockState;       /* current DOOR_STATE_* value          */
static uint8_t  doorInitialised;     /* set once DoorControl_Init has run   */
static uint16_t doorSupplyVoltage;   /* latest measured supply voltage (mV) */

/* External hooks provided by the board support package. */
extern uint8_t  Bsp_ReadDoorSwitch(void);     /* 1 = closed, 0 = open  */
extern uint16_t Bsp_ReadSupplyVoltage(void);  /* supply voltage in mV  */

void DoorControl_Init(void)
{
    doorLockState     = DOOR_STATE_UNLOCKED;
    doorSupplyVoltage = 0u;
    doorInitialised   = 1u;
}

void DoorControl_10ms(void)
{
    uint8_t switchClosed;

    if (doorInitialised == 0u)
    {
        return;
    }

    doorSupplyVoltage = Bsp_ReadSupplyVoltage();
    switchClosed      = Bsp_ReadDoorSwitch();

    if (doorSupplyVoltage < DOOR_LOCK_MIN_VOLTAGE)
    {
        /* Under-voltage: do not actuate, flag a fault. */
        doorLockState = DOOR_STATE_FAULT;
    }
    else if (switchClosed != 0u)
    {
        doorLockState = DOOR_STATE_LOCKED;
    }
    else
    {
        doorLockState = DOOR_STATE_UNLOCKED;
    }
}

uint8_t DoorControl_GetLockState(void)
{
    return doorLockState;
}
