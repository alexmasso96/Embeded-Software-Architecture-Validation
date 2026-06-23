#include "vcu_all.h"

/* VCU top-level scheduler (release R2.0).
 * Calls each present component/module Step() once per cycle. */

static uint32_t g_vcu_tick;

void Vcu_Bcm_Cyclic(void)
{
    Bcm_Lighting_Step();
    Bcm_Doors_Step();
    Bcm_Wipers_Step();
    Bcm_Windows_Step();
    Bcm_Mirrors_Step();
}

void Vcu_Pwt_Cyclic(void)
{
    Pwt_Torque_Step();
    Pwt_Throttle_Step();
    Pwt_Gearbox_Step();
    Pwt_Cruise_Step();
}

void Vcu_Bms_Cyclic(void)
{
    Bms_Cellmon_Step();
    Bms_Soc_Step();
    Bms_Balancing_Step();
    Bms_Contactor_Step();
}

void Vcu_Thm_Cyclic(void)
{
    Thm_Coolant_Step();
    Thm_Hvac_Step();
    Thm_Pump_Step();
    Thm_Fan_Step();
}

void Vcu_Chs_Cyclic(void)
{
    Chs_Abs_Step();
    Chs_Traction_Step();
    Chs_Steering_Step();
}

void Vcu_Diag_Cyclic(void)
{
    Diag_Dtc_Step();
    Diag_Freezeframe_Step();
    Diag_Uds_Step();
    Diag_Monitor_Step();
}

void Vcu_Com_Cyclic(void)
{
    Com_Canrouter_Step();
    Com_Linmaster_Step();
    Com_Signaldb_Step();
    Com_Netmon_Step();
}

void Vcu_InitAll(void)
{
    Bcm_Lighting_Init(0);
    Bcm_Doors_Init(0);
    Bcm_Wipers_Init(0);
    Bcm_Windows_Init(0);
    Bcm_Mirrors_Init(0);
    Pwt_Torque_Init(0);
    Pwt_Throttle_Init(0);
    Pwt_Gearbox_Init(0);
    Pwt_Cruise_Init(0);
    Bms_Cellmon_Init(0);
    Bms_Soc_Init(0);
    Bms_Balancing_Init(0);
    Bms_Contactor_Init(0);
    Thm_Coolant_Init(0);
    Thm_Hvac_Init(0);
    Thm_Pump_Init(0);
    Thm_Fan_Init(0);
    Chs_Abs_Init(0);
    Chs_Traction_Init(0);
    Chs_Steering_Init(0);
    Diag_Dtc_Init(0);
    Diag_Freezeframe_Init(0);
    Diag_Uds_Init(0);
    Diag_Monitor_Init(0);
    Com_Canrouter_Init(0);
    Com_Linmaster_Init(0);
    Com_Signaldb_Init(0);
    Com_Netmon_Init(0);
}

/* REQ-VCU-040: the 10ms task shall service every active component. */
void Vcu_Cyclic10ms(void)
{
    g_vcu_tick++;
    Vcu_Bcm_Cyclic();
    Vcu_Pwt_Cyclic();
    Vcu_Bms_Cyclic();
    Vcu_Thm_Cyclic();
    Vcu_Chs_Cyclic();
    Vcu_Diag_Cyclic();
    Vcu_Com_Cyclic();
}

uint32_t Vcu_GetTick(void)
{
    return g_vcu_tick;
}
