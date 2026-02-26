general_agent_prompt = """
You are the One Reside Concierge, currently assisting a customer who is exploring **{brand_name}**.

## About the Brand

- **Brand Name:** {brand_name}
- **Description:** {brand_description}
- **Categories Offered:** {categories_offered}
- **Product Types:** {product_types}
- **Consultation Available:** {consultation_available}
- **Working Hours:** {working_hours}

## Your Role

You are the brand's voice inside One Reside. You know this brand well and speak about it with warmth and confidence — like a knowledgeable friend who works closely with the brand, not a salesperson reading from a script.

You handle:
- Brand story, philosophy, and design approach
- Materials, craftsmanship, and process questions
- General inquiries about what the brand offers
- Greetings and welcome messages
- Scheduling consultations or callbacks (for custom products)

## Tools Available

You have access to one tool:

**brand_kb_search(query)** — Searches the brand's knowledge base for detailed information. Use this when the customer asks something specific that goes beyond the basic brand context above (e.g., detailed craftsmanship process, specific material sourcing, brand history, founder story, care instructions).

Do NOT make up information. If the knowledge base doesn't have an answer and you don't have it in your brand context, say so honestly:
*"I don't have that detail handy, but I can connect you with the {brand_name} team if you'd like."*

## Conversation Guidelines

**Tone:** Warm, confident, concise. You admire the brand but you're not a salesperson — you're a knowledgeable guide.

**Message length:** Keep it short. 2–4 sentences per message. Never write a wall of text.

**One question per message.** Never ask multiple questions at once.

**Greetings:** When the conversation starts (first message or restart), welcome the user:
> Hi 👋 Welcome to One Reside Concierge.
> You're viewing **{brand_name}**, known for {brand_short_pitch}.
> How can I help you today?

**Guiding to products:** If the user's questions suggest they're ready to explore products (e.g., "What chairs do you have?", "Show me something for my living room"), acknowledge their interest and let them know you'll switch to product recommendations. Do NOT try to recommend products yourself — that's the product recommender's job.
> Great choice — {brand_name} has some beautiful options for that. Let me help you find the right one.

**Scheduling consultations:** For custom products or when the user wants to talk to someone:
> Our One Reside in-house team will connect with you first to understand your space, budget, and timeline. After that, we'll bring **{brand_name}** in with a clear brief so you don't have to repeat anything.
> The team is available **{working_hours}**.
> What day and time works best for you?

When they confirm a time:
> Got it 👍 Our team will reach out on **[day] at [time]** and take this forward.

**Things to never do:**
- Never recommend specific products — that's the product recommender's job.
- Never invent brand details not in your context or knowledge base.
- Never discuss other brands.
- Never say "I'm an AI" or "As an AI assistant".
- Never use bullet points in conversation.
- Never ask more than one question per message.

**Emojis:** Use sparingly — only 👋 (welcome) and 👍 (confirmation).

## Brand Context

{brand_additional_context}
"""



def build_general_agent_prompt(brand: dict) -> str:
    """
    Takes a brand object from MongoDB and returns a fully populated
    general agent system prompt.

    Expected brand schema:
    {
        "brand_id": "portside-cafe",
        "brand_name": "PortsideCafé Studio",
        "brand_description": "Sculptural furniture designed to stand out in modern homes",
        "brand_short_pitch": "sculptural furniture designed to stand out in modern homes",
        "categories_offered": ["Accent Chair", "Sofa", "Coffee Table"],
        "product_types": ["ready_product"],
        "consultation_available": True,
        "working_hours": "Monday to Saturday, 10 am to 7 pm",
        "brand_additional_context": "Founded in 2018 in Mumbai..."  # optional, can be ""
    }
    """

    # Format list fields into readable strings
    categories = ", ".join(brand.get("categories_offered", []))
    
    product_types_raw = brand.get("product_types", [])
    product_types_map = {
        "ready_product": "Ready-to-order products",
        "custom_product": "Custom/bespoke pieces"
    }
    product_types = ", ".join([product_types_map.get(pt, pt) for pt in product_types_raw])

    consultation = "Yes" if brand.get("consultation_available", False) else "No"

    prompt = general_agent_prompt.format(
        brand_name=brand.get("brand_name", ""),
        brand_description=brand.get("brand_description", ""),
        brand_short_pitch=brand.get("brand_short_pitch", brand.get("brand_description", "")),
        categories_offered=categories,
        product_types=product_types,
        consultation_available=consultation,
        working_hours=brand.get("working_hours", "Monday to Saturday, 10 am to 7 pm"),
        brand_additional_context=brand.get("brand_additional_context", "No additional context provided.")
    )

    return prompt


output_schema ={
    "format": {
      "type": "json_schema",
      "name": "whatsapp_message_list",
      "strict": True,
      "schema": {
        "type": "object",
        "properties": {
          "messages": {
            "type": "array",
            "description": "A list of short WhatsApp-style messages.",
            "minItems": 1,
            "maxItems": 3,
            "items": {
              "type": "string",
              "description": "A single short WhatsApp-style message.",
              "minLength": 1,
              "maxLength": 256
            }
          }
        },
        "required": [
          "messages"
        ],
        "additionalProperties": False
      }
    }
}


# ============================================================
# Example usage
# ============================================================

portside_cafe = {
    "brand_id": "portside-cafe",
    "brand_name": "PortsideCafé Studio",
    "brand_description": "Sculptural furniture designed to stand out in modern homes. Known for solid wood frames, hand-upholstered seating, and pieces that age well rather than follow trends.",
    "brand_short_pitch": "sculptural furniture designed to stand out in modern homes",
    "categories_offered": ["Accent Chair", "Sofa", "Coffee Table"],
    "product_types": ["ready_product"],
    "consultation_available": False,
    "working_hours": "Monday to Saturday, 10 am to 7 pm",
    "brand_additional_context": ""
}

design_pov = {
    "brand_id": "design-pov",
    "brand_name": "Design POV",
    "brand_description": "Clean, highly detailed custom wardrobes and interiors. Specializes in bespoke storage solutions tailored to individual spaces.",
    "brand_short_pitch": "clean, highly detailed custom wardrobes and interiors",
    "categories_offered": ["Wardrobe", "TV Unit"],
    "product_types": ["custom_product"],
    "consultation_available": True,
    "working_hours": "Monday to Saturday, 10 am to 7 pm",
    "brand_additional_context": ""
}


if __name__ == "__main__":
    # Generate prompt for PortsideCafé
    prompt = build_general_agent_prompt(portside_cafe)
    print("=" * 60)
    print("PORTSIDE CAFÉ — GENERAL AGENT PROMPT")
    print("=" * 60)
    print(prompt)

    print("\n\n")

    # Generate prompt for Design POV
    prompt = build_general_agent_prompt(design_pov)
    print("=" * 60)
    print("DESIGN POV — GENERAL AGENT PROMPT")
    print("=" * 60)
    print(prompt)