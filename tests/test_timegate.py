from football_predictor.timegate import filter_available_records


def test_filter_blocks_future_observed_records():
    records = [
        {"id": "old", "observed_at": "2026-04-28T18:00:00+00:00"},
        {"id": "future", "observed_at": "2026-04-28T21:00:00+00:00"},
    ]
    visible, audit = filter_available_records(records, "2026-04-28T20:00:00+00:00")
    assert [record["id"] for record in visible] == ["old"]
    assert audit["future_records"] == 1


def test_filter_blocks_untimestamped_time_sensitive_records():
    visible, audit = filter_available_records(
        [{"id": "lineup", "category": "lineup"}],
        "2026-04-28T20:00:00+00:00",
        time_sensitive_categories={"lineup"},
    )
    assert visible == []
    assert audit["untimestamped_records"] == 1


def test_projection_with_future_effective_at_is_allowed_when_observed_before_checkpoint():
    records = [
        {
            "id": "projected_lineup",
            "category": "lineup",
            "confidence": "projected",
            "observed_at": "2026-04-28T12:00:00+00:00",
            "effective_at": "2026-04-28T19:00:00+00:00",
        }
    ]
    visible, audit = filter_available_records(records, "2026-04-28T18:00:00+00:00")
    assert [record["id"] for record in visible] == ["projected_lineup"]
    assert audit["future_records"] == 0
