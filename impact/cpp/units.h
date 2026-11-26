// Shared helpers used by several components (a deliberate shared dependency).
#pragma once
inline int age_ms(int now, int stamp) {
  return now - stamp;
}
inline int clamp_int(int v, int lo, int hi) {
  if (v < lo) {
    return lo;
  }
  if (v > hi) {
    return hi;
  }
  return v;
}
