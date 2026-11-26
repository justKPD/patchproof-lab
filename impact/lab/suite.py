"""The system's own regression suite: the tests whose selection is studied.

Written the way a component owner typically writes them: mostly expected scenarios,
a few edges, and integration tests through the composed pipeline. It is intentionally
NOT exhaustive; surviving mutants are reported later as concrete missing test goals.

DECLARED lists what each test's author would put in a hand-maintained dependency
manifest (the approach in the original PatchProof workspace): the component file the
test targets, without transitive or shared-header dependencies.
"""


def t_sensor_nominal_accepts(lib):
    assert lib.validate_sample(1000, 990, 2, 1, 1, 1, 100) == 0


def t_sensor_invalid_flag(lib):
    assert lib.validate_sample(1000, 990, 2, 1, 0, 1, 100) & 1


def t_sensor_disabled_flag(lib):
    assert lib.validate_sample(1000, 990, 2, 1, 1, 0, 100) & 2


def t_sensor_future_flag(lib):
    assert lib.validate_sample(1000, 1010, 2, 1, 1, 1, 100) & 4


def t_sensor_long_expired(lib):
    assert lib.validate_sample(1000, 500, 2, 1, 1, 1, 100) & 8


def t_sensor_replay_flag(lib):
    assert lib.validate_sample(1000, 990, 1, 1, 1, 1, 100) & 16


def t_limiter_passthrough(lib):
    assert lib.clamp_command(50, 80) == 50


def t_limiter_upper(lib):
    assert lib.clamp_command(200, 80) == 80


def t_limiter_negative(lib):
    assert lib.clamp_command(-5, 80) == 0


def t_rate_small_step(lib):
    assert lib.rate_limit(0, 10, 25) == 10


def t_rate_limited_up(lib):
    assert lib.rate_limit(0, 100, 25) == 25


def t_rate_limited_down(lib):
    assert lib.rate_limit(100, 0, 25) == 75


def t_rate_default_step(lib):
    assert lib.rate_limit(0, 100, 0) == 25


def t_pipe_nominal(lib):
    assert lib.pipeline_step(1000, 990, 2, 1, 1, 1, 50, 80, 100, 40, 25) == 50


def t_pipe_reject_is_zero(lib):
    assert lib.pipeline_step(1000, 990, 2, 1, 0, 1, 50, 80, 100, 80, 25) == 0


def t_pipe_clamp_then_rate(lib):
    assert lib.pipeline_step(1000, 990, 2, 1, 1, 1, 500, 80, 100, 70, 25) == 80


def t_pipe_boundary_expired(lib):
    assert lib.pipeline_step(1000, 900, 2, 1, 1, 1, 50, 80, 100, 40, 25) == 0


def t_pipe_ramp_sequence(lib):
    prev, seen = 0, []
    for i in range(5):
        prev = lib.pipeline_step(1000 + i, 995 + i, 2 + i, 1 + i, 1, 1, 100, 80, 100, prev, 25)
        seen.append(prev)
    assert seen == [25, 50, 75, 80, 80]


def t_tel_status_encoding(lib):
    assert lib.telemetry_dispatch(0, 8, 5) == (8 << 16) | 5


def t_tel_age(lib):
    assert lib.telemetry_dispatch(1, 1000, 990) == 10


def t_tel_age_future(lib):
    assert lib.telemetry_dispatch(1, 990, 1000) == -1


def t_tel_bad_kind(lib):
    assert lib.telemetry_dispatch(2, 0, 0) == -2


TESTS = {name: fn for name, fn in globals().items() if name.startswith("t_") and callable(fn)}

DECLARED = {
    name: [{"sensor": "sensor.cpp", "limiter": "limiter.cpp", "rate": "rate.cpp",
            "pipe": "pipeline.cpp", "tel": "telemetry.cpp"}[name.split("_")[1]]]
    for name in TESTS
}
