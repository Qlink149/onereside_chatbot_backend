"""CASES 13–14 — agent request and human takeover."""

import pytest

from onereside_chatbot.constants import UNSUPPORTED_TYPE_RESPONSES, AGENT_REQUEST_RESPONSES
from tests.characterisation.conftest import (
    build_gupshup_payload,
    text_message,
)


@pytest.mark.asyncio
async def test_case13_agent_request_sets_flag_notifies_support_bot_replies(
    test_phone,
    run_inbound,
    openai_queue,
    classifier_agent_request,
    gupshup_calls,
):
    gupshup_calls.clear()

    data = await run_inbound(
        build_gupshup_payload(
            test_phone,
            text_message("I want to talk to a human", test_phone),
        )
    )

    from tests.db_guard import idac

    user = idac.find_one({"phone_number": test_phone})
    assert user.get("agent_request") is True

    support_calls = [c for c in gupshup_calls if "template/msg" in c["url"]]
    assert len(support_calls) >= 1

    assert data is not None
    assert data.get("bot_response")
    assert len(data["bot_response"]) > 0


@pytest.mark.asyncio
async def test_case14_active_takeover_suppresses_bot_and_publishes(
    test_phone,
    run_inbound,
    seed_user,
    pubsub_events,
):
    seed_user(human_takeover={"active": True, "taken_by": "admin", "taken_at": 1})

    data = await run_inbound(
        build_gupshup_payload(
            test_phone,
            text_message("Hello while human is active", test_phone),
        )
    )

    assert data is None or not data.get("bot_response")

    user_msgs = [
        e for e in pubsub_events if e["event"].get("type") == "user_message"
    ]
    assert len(user_msgs) >= 1
