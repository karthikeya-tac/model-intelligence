from experiments.router_v2.features import difficulty_score, extract_features


def test_code_and_math_detection():
    assert extract_features("```python\ndef f():\n    return 1\n```").has_code
    assert extract_features("solve 2 + 2 = x").has_math
    assert not extract_features("say hello to me").has_code


def test_difficulty_monotonic_in_signal():
    easy = extract_features("hi there")
    hard = extract_features(
        "design and implement a distributed rate limiter; it must be thread-safe, "
        "handle backpressure, and you should ensure exactly-once semantics, then add tests"
    )
    assert difficulty_score(hard, {}) > difficulty_score(easy, {})


def test_trivial_is_low_difficulty():
    assert difficulty_score(extract_features("hi there"), {}) < 0.3


def test_deterministic():
    a = extract_features("refactor this function and add edge-case tests")
    b = extract_features("refactor this function and add edge-case tests")
    assert a == b
