// Status encoding reached through a function-pointer table (static call graphs often miss this).
#include "config.h"
#include "units.h"
static int encode_status(int flags, int cmd) {
  return (flags << kStatusShift) | (cmd & 0xFFFF);
}
static int encode_age(int now, int stamp) {
  int a = age_ms(now, stamp);
  return a < 0 ? -1 : a;
}
typedef int (*encoder)(int, int);
static const encoder kEncoders[2] = {encode_status, encode_age};
extern "C" int telemetry_dispatch(int kind, int a, int b) {
  if (kind < 0 || kind > 1) {
    return -2;
  }
  return kEncoders[kind](a, b);
}
