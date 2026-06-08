#ifndef WLC_TYPES_H
#define WLC_TYPES_H

#include <stdint.h>

/* REQ-WLC-010: Window-lift configuration shall be calibratable. */
typedef struct {
    uint16_t max_duty;         /* maximum PWM duty 0..1000           */
    uint16_t current_limit_ma; /* over-current trip point (mA)       */
    uint8_t  pinch_enabled;    /* 1 = anti-pinch protection active   */
} WLC_Config_t;

/* REQ-WLC-011: Runtime state shall be observable. */
typedef struct {
    uint8_t  phase;        /* one of WLC_Phase_t                  */
    uint16_t position;     /* scaled hall position 0..1000        */
    uint16_t current_ma;   /* last measured motor current (mA)    */
    uint8_t  pinch_flag;   /* 1 = pinch event latched             */
    uint16_t reverse_count;/* REQ-WLC-050: auto-reverse counter   */
} WLC_State_t;

typedef enum {
    WLC_IDLE         = 0,
    WLC_MOVING_UP    = 1,
    WLC_MOVING_DOWN  = 2,
    WLC_PINCH_STOP   = 3,
    WLC_AUTO_REVERSE = 4
} WLC_Phase_t;

#endif /* WLC_TYPES_H */
