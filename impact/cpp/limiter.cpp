// R-LIMIT: accepted request clamped to [0, limit]
#include "units.h"
extern "C" int clamp_command(int requested, int limit) {
  return clamp_int(requested, 0, limit);
}
