// Authored reference fixture. No Bosch code or machine connection.
#ifndef PATCH
#define PATCH 0
#endif
extern "C" {
int reason(int now, int stamp, int seq, int last, int valid, int enabled,
           int requested, int limit, int timeout) {
  (void)requested; (void)limit; (void)seq; (void)last; (void)enabled;
  int flags = 0;
  if (valid == 0) { flags |= 1; }
#if PATCH != 5
  if (enabled == 0) { flags |= 2; }
#endif
#if PATCH != 2
  if (stamp > now) { flags |= 4; }
#endif
#if PATCH == 1
  if (now - stamp > timeout) { flags |= 8; }
#else
  if (now - stamp >= timeout) { flags |= 8; }
#endif
#if PATCH != 4
  if (seq <= last) { flags |= 16; }
#endif
  return flags;
}
int command(int now, int stamp, int seq, int last, int valid, int enabled,
            int requested, int limit, int timeout) {
  if (reason(now, stamp, seq, last, valid, enabled, requested, limit, timeout) != 0) {
    return 0;
  }
#if PATCH == 3
  return requested < 0 ? 0 : requested;
#elif PATCH == 6
  return requested < 0 ? 0 : (requested > limit ? limit + 1 : requested);
#else
  return requested < 0 ? 0 : (requested > limit ? limit : requested);
#endif
}
}

