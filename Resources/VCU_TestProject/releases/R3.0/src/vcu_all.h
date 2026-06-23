#ifndef VCU_ALL_H
#define VCU_ALL_H

#include <stdint.h>

#include "body_control/lighting.h"
#include "body_control/doors.h"
#include "body_control/wipers.h"
#include "body_control/windows.h"
#include "body_control/mirrors.h"
#include "powertrain/torque.h"
#include "powertrain/throttle.h"
#include "powertrain/gearbox.h"
#include "powertrain/cruise.h"
#include "battery_mgmt/cellmon.h"
#include "battery_mgmt/soc.h"
#include "battery_mgmt/balancing.h"
#include "battery_mgmt/contactor.h"
#include "battery_mgmt/thermrunaway.h"
#include "thermal_mgmt/coolant.h"
#include "thermal_mgmt/hvac.h"
#include "thermal_mgmt/pump.h"
#include "thermal_mgmt/fan.h"
#include "chassis_control/abs.h"
#include "chassis_control/traction.h"
#include "chassis_control/steering.h"
#include "diagnostics/dtc.h"
#include "diagnostics/freezeframe.h"
#include "diagnostics/uds.h"
#include "diagnostics/monitor.h"
#include "diagnostics/security.h"
#include "comm_gateway/canrouter.h"
#include "comm_gateway/linmaster.h"
#include "comm_gateway/signaldb.h"
#include "comm_gateway/netmon.h"
#include "charging_ctrl/acdc.h"
#include "charging_ctrl/sequencer.h"
#include "charging_ctrl/pilot.h"
#include "charging_ctrl/metering.h"

/* top-level scheduler */
void Vcu_Bcm_Cyclic(void);
void Vcu_Pwt_Cyclic(void);
void Vcu_Bms_Cyclic(void);
void Vcu_Thm_Cyclic(void);
void Vcu_Chs_Cyclic(void);
void Vcu_Diag_Cyclic(void);
void Vcu_Com_Cyclic(void);
void Vcu_Chg_Cyclic(void);
void Vcu_InitAll(void);
void Vcu_Cyclic10ms(void);
uint32_t Vcu_GetTick(void);

#endif /* VCU_ALL_H */
