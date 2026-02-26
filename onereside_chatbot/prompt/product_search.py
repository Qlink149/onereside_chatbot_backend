from onereside_chatbot.database.collections import product


product_recommender_prompt = """
You are the One Reside Product Concierge for **{brand_name}**.

## Brand Context
- **Brand:** {brand_name} — {brand_description}
- **Categories:** {categories_offered}
- **Price Range:** {price_range}
- **Style Tags:** {all_style_tags}
- **Colors:** {all_colors}
- **Rooms:** {all_rooms}

## What You Do
Guide the customer to the right product. Ask one question at a time — skip any already answered:

1. **Category** (if multiple) — "Are you looking for a {categories_as_options}?"
2. **Room** — "Which room is this for?"
3. **Budget** — "This collection ranges from {price_range}. Does that sit comfortably?"
4. **Style** — Simple A/B choice based on available tags.

Once you have enough context, call a tool. Never recommend products yourself.

## Tools

**semantic_search** — When the user describes feelings/vibes.
```json
{{"tool": "semantic_search", "query": "<descriptive phrase>", "brand_id": "{brand_id}", "exclude_ids": []}}
```

**keyword_search** — When the user gives specific filters.
```json
{{"tool": "keyword_search", "brand_id": "{brand_id}", "filters": {{"category": null, "ideal_for": null, "price_min": null, "price_max": null, "style_tags": [], "materials": null, "colors": null}}, "exclude_ids": []}}
```

## Rejection Handling
- **1st rejection:** Adjust params, search again.
- **2nd rejection:** Stop. Ask a reframing question first.
- **3rd+:** If exhausted, offer to connect with in-house team.

## Rules
- One question per message. 2–4 sentences max.
- Never show products — only call tools.
- Never invent products or discuss other brands.
"""


#  PRODUCT PRESENTER
product_presenter_prompt = """
You receive search results and customer context. Pick the best product and write the message text only.

## You Receive
- **search_results**: Up to 3 products
- **user_preferences**: Room, style, budget
- **rejection_count**: Current cycle rejections
- **rejected_ids**: Already rejected product IDs

## Pick the Best Product
- Match user preferences first.
- Avoid similarity to rejected products.
- After 2+ rejections, pick with strongest confidence.

## Output Format

Line 1: [PRODUCT_ID: <id>] (or [PRODUCT_ID: none] if nothing fits)
Line 2 onwards: The message text only. No image links. No buttons. No JSON. Just the text to send.

## Message Rules

- 4–6 sentences max. No bullet points. No feature dumps.
- Lead with WHY it fits, not what it's made of.
- Always include price (₹ format) and delivery (weeks).
- End with a soft close + escape hatch.

**After 0 rejections:**
Introduce the product confidently. Explain why it fits. Price + delivery. Ask if they'd like to proceed or see another option.

**After 1 rejection:**
Signal a different direction. Explain how this differs. Price + delivery. Soft close.

**After 2+ rejections:**
Present with conviction: "Based on that, this is the piece I'd recommend." Rationale tied to reframe answer. Price + delivery. Final option escape.

**Custom products:**
Note it's custom and tailored. What makes it special. Starting price + timeline. Suggest scheduling a consultation.

**No match:**
Be honest. Suggest adjusting the search or connecting with the in-house team.
"""


def fetch_brand_metadata(brand_id: str) -> dict:
    """
    Uses MongoDB aggregation to extract unique tags, colors, 
    rooms, and price range — without fetching full product docs.
    """
    pipeline = [
        {"$match": {"brand_id": brand_id}},
        {"$group": {
            "_id": None,
            "all_style_tags": {"$addToSet": "$style_tags"},
            "all_colors": {"$addToSet": "$colors_available"},
            "all_rooms": {"$addToSet": "$ideal_for"},
            "min_price": {"$min": {
                "$ifNull": ["$price_inr", "$price_starting_inr"]
            }},
            "max_price": {"$max": {
                "$ifNull": ["$price_inr", "$price_starting_inr"]
            }},
        }}
    ]

    result = list(product.aggregate(pipeline))

    if not result:
        return {
            "all_style_tags": "Various",
            "all_colors": "Various",
            "all_rooms": "Various",
            "price_range": "Not available",
        }

    data = result[0]

    style_tags = sorted(set(t for arr in data.get("all_style_tags", []) for t in arr))
    colors = sorted(set(c for arr in data.get("all_colors", []) for c in arr))
    rooms = sorted(set(r for arr in data.get("all_rooms", []) for r in arr))

    min_p = data.get("min_price")
    max_p = data.get("max_price")
    price_range = f"₹{min_p:,.0f} to ₹{max_p:,.0f}" if min_p and max_p else "Not available"

    return {
        "all_style_tags": ", ".join(style_tags) or "Various",
        "all_colors": ", ".join(colors) or "Various",
        "all_rooms": ", ".join(rooms) or "Various",
        "price_range": price_range,
    }


def build_product_recommender_prompt(brand: dict) -> str:
    """Returns the recommender prompt."""
    brand_id = brand.get("brand_id", "")
    meta = fetch_brand_metadata(brand_id)  

    categories = brand.get("categories_offered", [])
    if len(categories) > 1:
        categories_as_options = ", ".join(categories[:-1]) + f", or {categories[-1]}"
    else:
        categories_as_options = categories[0] if categories else "something"

    return product_recommender_prompt.format(
        brand_name=brand.get("brand_name", ""),
        brand_id=brand_id,
        brand_description=brand.get("brand_description", ""),
        categories_offered=", ".join(categories),
        categories_as_options=categories_as_options,
        price_range=meta["price_range"],
        all_style_tags=meta["all_style_tags"],
        all_colors=meta["all_colors"],
        all_rooms=meta["all_rooms"],
    )

def build_product_presenter_prompt(brand_name: str) -> str:
    """Returns the presenter prompt with brand name filled in."""
    return product_presenter_prompt.replace("{brand_name}", brand_name)


# ________________________________________
# output schema
output_schema = {
    "format": {
        "type": "json_schema",
        "name": "whatsapp_message",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "A single short WhatsApp-style message."
                }
            },
            "required": ["message"],
            "additionalProperties": False
        }
    }
}

presenter_output_schema = {
    "format": {
        "type": "json_schema",
        "name": "product_presenter_response",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "product_id": {
                    "type": ["string", "null"],
                    "description": "The selected product ID, or null if no product fits."
                },
                "message": {
                    "type": "string",
                    "description": "The message text to send to the customer."
                }
            },
            "required": ["product_id", "message"],
            "additionalProperties": False
        }
    }
}

# _________________________________________
# tool
semantic_search_tool = {
    "type": "function",
    "name": "semantic_search",
    "description": "Search products by semantic similarity when the user describes what they want in subjective, feeling-based, or descriptive language. Examples: 'something gallery-like', 'warm and inviting', 'Japanese minimalism vibes'.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language description of what the user wants, combining style, feeling, and preferences gathered from the conversation."
            }
        },
        "required": ["query"]
    }
}

keyword_search_tool = {
    "type": "function",
    "name": "keyword_search",
    "description": "Search products by structured filters when the user gives specific preferences like category, material, color, price range, or room type. Examples: 'wooden accent chair under 3 lakhs', 'black marble coffee table'.",
    "parameters": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "Product category. e.g. Accent Chair, Sofa, Coffee Table, Wardrobe, TV Unit."
            },
            "ideal_for": {
                "type": "string",
                "description": "Room type. e.g. Living Room, Bedroom, Study, Walk-in Closet."
            },
            "price_min": {
                "type": "number",
                "description": "Minimum budget in INR."
            },
            "price_max": {
                "type": "number",
                "description": "Maximum budget in INR."
            },
            "style_tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Style descriptors. e.g. bold, sculptural, minimal, modern, luxury."
            },
            "materials": {
                "type": "string",
                "description": "Preferred material. e.g. teak, marble, metal, velvet."
            },
            "colors": {
                "type": "string",
                "description": "Preferred color. e.g. Emerald Green, Charcoal Grey, Black Marble."
            }
        },
        "required": []
    }
}