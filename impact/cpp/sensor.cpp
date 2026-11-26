// R-VALID, R-ENABLE, R-FUTURE, R-FRESH, R-ORDER
#include "units.h"
extern "C" int validate_sample(int now, int stamp, int seq, int last,
                               int valid, int enabled, int timeout) {
  int flags = 0;
  if (valid == 0) {
    flags |= 1;
  }
  if (enabled == 0) {
    flags |= 2;
  }
  if (stamp > now) {
    flags |= 4;
  }
  if (age_ms(now, stamp) >= timeout) {
    flags |= 8;
  }
  if (seq <= last) {
    flags |= 16;
  }
  return flags;
}
