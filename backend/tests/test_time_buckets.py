from echo.time_buckets import time_bucket


def test_buckets():
    assert time_bucket(7) == "morning"
    assert time_bucket(14) == "afternoon"
    assert time_bucket(20) == "evening"
    assert time_bucket(2) == "night"
