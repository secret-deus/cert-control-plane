from app.models import Agent, Rollout, RolloutItem


def test_agent_status_enum_persists_values():
    assert Agent.__table__.c.status.type.enums == [
        "pending_approval",
        "active",
        "revoked",
    ]


def test_rollout_status_enum_persists_values():
    assert Rollout.__table__.c.status.type.enums == [
        "pending",
        "running",
        "paused",
        "completed",
        "failed",
        "rolled_back",
    ]


def test_rollout_item_status_enum_persists_values():
    assert RolloutItem.__table__.c.status.type.enums == [
        "pending",
        "in_progress",
        "completed",
        "failed",
        "rolled_back",
    ]
