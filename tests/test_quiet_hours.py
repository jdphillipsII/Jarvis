import pytest
from core.quiet_hours import QuietHourLearner, hour_of_week, describe


def test_bucket_maths():
    assert hour_of_week(0, 0) == 0 and hour_of_week(6, 23) == 167
    assert describe(hour_of_week(2, 9)) == "Wed 09:00"
    with pytest.raises(ValueError):
        hour_of_week(7, 0)


def test_needs_enough_samples_before_concluding_anything():
    q = QuietHourLearner(min_samples=3)
    q.record(10, True); q.record(10, True)
    assert q.suggestions() == []          # two rejections is not a pattern
    q.record(10, True)
    assert q.suggestions() == [10]


def test_occasional_dismissal_is_not_a_quiet_hour():
    q = QuietHourLearner()
    for d in (True, False, False, False, False):
        q.record(20, d)
    assert q.suggestions() == []


def test_distinguishes_sunday_morning_from_wednesday_morning():
    """The reason for 168 buckets rather than a start/end time."""
    q = QuietHourLearner()
    sun, wed = hour_of_week(6, 9), hour_of_week(2, 9)
    for _ in range(5):
        q.record(sun, True)
        q.record(wed, False)
    assert q.suggestions() == [sun]


def test_explain_is_human_readable():
    q = QuietHourLearner()
    for _ in range(4):
        q.record(hour_of_week(0, 7), True)
    assert q.explain() == ["Mon 07:00 - dismissed 4/4"]


def test_round_trips_through_json():
    q = QuietHourLearner(dismissal_threshold=0.9, min_samples=2)
    q.record(5, True); q.record(5, True); q.record(9, False)
    back = QuietHourLearner.from_json(q.to_json())
    assert back.buckets == q.buckets
    assert back.suggestions() == q.suggestions()
    assert back.dismissal_threshold == 0.9
