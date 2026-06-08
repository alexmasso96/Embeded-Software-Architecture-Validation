#include "wlc_sensor.h"

/* Module-private state. */
static uint16_t s_raw_adc;  /* last raw ADC sample */

/* REQ-WLC-020: Hall position shall be scaled to a 0..1000 range. */
static uint16_t WLC_Scale(uint16_t raw)
{
    return (uint16_t)((uint32_t)raw * 1000u / 4095u);
}

uint16_t WLC_ReadHallPosition(void)
{
    s_raw_adc = 2048u;            /* HW_ADC_Read(HALL_CH) */
    return WLC_Scale(s_raw_adc);
}

/* REQ-WLC-021: Motor current shall be measured in milliamps. */
uint16_t WLC_ReadCurrent(void)
{
    uint16_t raw = 100u;          /* HW_ADC_Read(CURR_CH) */
    return (uint16_t)((uint32_t)raw * 10u);
}
