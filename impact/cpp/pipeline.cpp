// Composition: validate -> clamp -> rate-limit. Rejection is fail-safe (immediate zero).
extern "C" int validate_sample(int, int, int, int, int, int, int);
extern "C" int clamp_command(int, int);
extern "C" int rate_limit(int, int, int);
extern "C" int pipeline_step(int now, int stamp, int seq, int last, int valid,
                             int enabled, int requested, int limit, int timeout,
                             int prev, int max_step) {
  if (validate_sample(now, stamp, seq, last, valid, enabled, timeout) != 0) {
    return 0;
  }
  int target = clamp_command(requested, limit);
  return rate_limit(prev, target, max_step);
}
