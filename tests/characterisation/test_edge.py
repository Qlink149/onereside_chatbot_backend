"""CASES 15–16 — edge characterisation."""

import pytest

from onereside_chatbot.constants import UNSUPPORTED_TYPE_RESPONSES
from tests.characterisation.conftest import (
    build_gupshup_payload,
    image_message,
    text_message,
)


@pytest.mark.asyncio
async def test_case15_image_inbound_unsupported_text_response(
    test_phone,
    run_inbound,
):
    data = await run_inbound(
        build_gupshup_payload(test_phone, image_message(test_phone))
    )

    texts = [i for i in data["bot_response"] if i.get("type") == "text"]
    assert texts

    assert texts[0]["text"] in UNSUPPORTED_TYPE_RESPONSES


@pytest.mark.asyncio
async def test_case16_stop_returns_unsubscribe_ack(
    test_phone,
    run_inbound,
):
    data = await run_inbound(
        build_gupshup_payload(test_phone, text_message("stop", test_phone))
    )

    texts = [i.get("text", "") for i in data["bot_response"] if i.get("type") == "text"]
    assert any("unsubscribed" in t.lower() for t in texts)
