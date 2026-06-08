#ifndef WLC_MAIN_H
#define WLC_MAIN_H

#include "wlc_types.h"

void               WLC_Init(const WLC_Config_t *cfg);
void               WLC_Cyclic(void);
const WLC_State_t *WLC_GetState(void);

#endif /* WLC_MAIN_H */
