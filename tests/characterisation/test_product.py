"""CASES 2–5 — product search characterisation."""

import json

import pytest

from tests.characterisation.conftest import (
    build_gupshup_payload,
    make_openai_function_call,
    make_openai_message,
    make_openai_response,
    text_message,
)


def _queue_product_fetch(openai_queue, product_id: str, presenter: dict):
    """Classifier already queued → recommender get_product_by_id → presenter."""
    openai_queue.append(
        make_openai_response(
            make_openai_function_call(
                "get_product_by_id",
                {"product_id": product_id, "is_new_topic": False},
            )
        )
    )
    openai_queue.append(
        make_openai_response(make_openai_message(json.dumps(presenter)))
    )


@pytest.mark.asyncio
async def test_case2_product_search_contains_media(
    test_phone,
    run_inbound,
    openai_queue,
    classifier_product,
    product_with_price,
):
    pid = product_with_price["product_id"]
    _queue_product_fetch(
        openai_queue,
        pid,
        {
            "product_id": pid,
            "product_ids": None,
            "message": "Here is a priced chair.",
            "add_needs": [],
            "remove_needs": [],
        },
    )

    data = await run_inbound(
        build_gupshup_payload(
            test_phone, text_message("Show me a chair", test_phone)
        )
    )

    assert any(item.get("type") == "media" for item in data["bot_response"])


@pytest.mark.asyncio
async def test_case3_product_with_price_buy_quickreply(
    test_phone,
    run_inbound,
    openai_queue,
    classifier_product,
    product_with_price,
):
    pid = product_with_price["product_id"]
    _queue_product_fetch(
        openai_queue,
        pid,
        {
            "product_id": pid,
            "product_ids": None,
            "message": "Priced product for you.",
            "add_needs": [],
            "remove_needs": [],
        },
    )

    data = await run_inbound(
        build_gupshup_payload(
            test_phone, text_message("I want that chair", test_phone)
        )
    )

    quickreplies = [i for i in data["bot_response"] if i.get("type") == "quickreply"]
    assert len(quickreplies) >= 1

    qr = quickreplies[0]
    assert len(qr["options"]) == 1

    assert qr["options"][0]["title"] == "Buy"

    assert qr["msgid"].startswith("buy$")


@pytest.mark.asyncio
async def test_case4_product_without_price_enquire_now_but_buy_msgid(
    test_phone,
    run_inbound,
    openai_queue,
    classifier_product,
    product_without_price,
):
    pid = product_without_price["product_id"]
    _queue_product_fetch(
        openai_queue,
        pid,
        {
            "product_id": pid,
            "product_ids": None,
            "message": "No-price product for you.",
            "add_needs": [],
            "remove_needs": [],
        },
    )

    data = await run_inbound(
        build_gupshup_payload(
            test_phone, text_message("Show me that lamp", test_phone)
        )
    )

    quickreplies = [i for i in data["bot_response"] if i.get("type") == "quickreply"]
    assert len(quickreplies) >= 1

    qr = quickreplies[0]
    assert len(qr["options"]) == 1

    assert qr["options"][0]["title"] == "Enquire Now"

    # INTENTIONAL: msgid is buy$ even for no-price products.
    # product_checkout.py routes on msgid. Do not "fix" this.
    assert qr["msgid"].startswith("buy$")


@pytest.mark.asyncio
async def test_case5_comparison_media_then_text_no_quickreply(
    test_phone,
    run_inbound,
    openai_queue,
    classifier_product,
    product_with_price,
    product_b,
):
    p1 = product_with_price["product_id"]
    p2 = product_b["product_id"]

    openai_queue.append(
        make_openai_response(
            make_openai_function_call(
                "compare_products",
                {
                    "product_id_1": p1,
                    "product_id_2": p2,
                    "is_new_topic": False,
                },
            )
        )
    )
    openai_queue.append(
        make_openai_response(
            make_openai_message(
                json.dumps(
                    {
                        "product_id": None,
                        "product_ids": [p1, p2],
                        "message": "Here is a side-by-side comparison.",
                        "add_needs": [],
                        "remove_needs": [],
                    }
                )
            )
        )
    )

    data = await run_inbound(
        build_gupshup_payload(
            test_phone, text_message("Compare these two", test_phone)
        )
    )

    bot = data["bot_response"]
    assert any(i.get("type") == "media" for i in bot)

    types = [i.get("type") for i in bot]
    last_media_idx = max(i for i, t in enumerate(types) if t == "media")
    text_idxs = [i for i, t in enumerate(types) if t == "text"]
    assert text_idxs
    assert text_idxs[0] > last_media_idx

    assert not any(i.get("type") == "quickreply" for i in bot)
