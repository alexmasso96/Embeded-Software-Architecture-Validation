#ifndef WLC_SAFETY_H
#define WLC_SAFETY_H

#include "wlc_types.h"

/* REQ-WLC-050: On pinch detection the window shall auto-reverse. */
void WLC_AutoReverse(WLC_State_t *state);

#endif /* WLC_SAFETY_H */
