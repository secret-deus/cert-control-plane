from app.models import Agent, Rollout, RolloutItem, AgentStatus, RolloutStatus, RolloutItemStatus


def test_agent_status_enum_persists_values():
    # SQLAlchemy stores enum names (uppercase) not values
    assert Agent.__table__.c.status.type.enums == [
        "PENDING_APPROVAL",
        "ACTIVE",
        "REVOKED",
    ]
    # But values are lowercase
    assert AgentStatus.PENDING_APPROVAL.value == "pending_approval"
    assert AgentStatus.ACTIVE.value == "active"
    assert AgentStatus.REVOKED.value == "revoked"


def test_rollout_status_enum_persists_values():
    assert Rollout.__table__.c.status.type.enums == [
        "PENDING",
        "RUNNING",
        "PAUSED",
        "COMPLETED",
        "FAILED",
        "ROLLED_BACK",
    ]
    assert RolloutStatus.PENDING.value == "pending"
    assert RolloutStatus.RUNNING.value == "running"


def test_rollout_item_status_enum_persists_values():
    assert RolloutItem.__table__.c.status.type.enums == [
        "PENDING",
        "IN_PROGRESS",
        "COMPLETED",
        "FAILED",
        "ROLLED_BACK",
    ]
    assert RolloutItemStatus.PENDING.value == "pending"
    assert RolloutItemStatus.IN_PROGRESS.value == "in_progress"
