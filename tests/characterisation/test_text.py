"""CASE 1 — free text inbound, new user."""

import pytest

from tests.characterisation.conftest import (
    build_gupshup_payload,
    make_openai_message,
    make_openai_response,
    text_message,
)
import json


@pytest.mark.asyncio
async def test_case1_free_text_new_user_creates_user_and_typed_bot_response(
    test_phone,
    run_inbound,
    openai_queue,
    classifier_one_reside,
):
    openai_queue.append(
        make_openai_response(
            make_openai_message(
                json.dumps({"message": "Welcome to OneReside characterisation."})
            )
        )
    )

    data = await run_inbound(
        build_gupshup_payload(test_phone, text_message("Hello there", test_phone))
    )

    from tests.db_guard import idac

    user = idac.find_one({"phone_number": test_phone})
    assert user is not None

    assert isinstance(data["bot_response"], list)

    for item in data["bot_response"]:
        assert "type" in item
