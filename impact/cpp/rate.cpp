// R-RATE: |out - prev| <= max_step; max_step <= 0 selects the configured default
#include "config.h"
#include "units.h"
extern "C" int rate_limit(int prev, int target, int max_step) {
  int step = max_step > 0 ? max_step : kDefaultMaxStep;
  int delta = clamp_int(target - prev, -step, step);
  return prev + delta;
}
