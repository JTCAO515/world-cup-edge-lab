from datetime import datetime


DEFAULT_TIME_SENSITIVE_CATEGORIES = {"injury", "lineup", "odds", "result", "weather"}


def parse_timestamp(value):
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def empty_audit():
    return {
        "future_records": 0,
        "untimestamped_records": 0,
        "visible_records": 0,
    }


def merge_audits(*audits):
    merged = empty_audit()
    for audit in audits:
        for key, value in audit.items():
            merged[key] = merged.get(key, 0) + value
    return merged


def filter_available_records(records, checkpoint_time, time_sensitive_categories=None):
    checkpoint = parse_timestamp(checkpoint_time)
    sensitive_categories = (
        set(time_sensitive_categories)
        if time_sensitive_categories is not None
        else DEFAULT_TIME_SENSITIVE_CATEGORIES
    )
    visible = []
    audit = empty_audit()

    for record in records:
        observed_at = parse_timestamp(record.get("observed_at"))
        effective_at = parse_timestamp(record.get("effective_at"))
        category = record.get("category")

        if observed_at is None and category in sensitive_categories:
            audit["untimestamped_records"] += 1
            continue

        if observed_at is not None and observed_at > checkpoint:
            audit["future_records"] += 1
            continue

        is_projection = record.get("confidence") == "projected"
        if effective_at is not None and effective_at > checkpoint and not is_projection:
            audit["future_records"] += 1
            continue

        visible.append(record)

    audit["visible_records"] = len(visible)
    return visible, audit
