# OneReside Bot — TODO

## Brand KB in Vector DB

**Idea:** Embed brand knowledge (FAQs, descriptions, context) into a separate Chroma collection (`brand_kb`) so agents can search it.

**Why:**
- When a user hasn't scanned any QR code and asks about a specific brand ("tell me about Kansso", "who founded this?", "what makes their bedding different?"), the `OneResideAgent` currently has zero brand knowledge and will hallucinate or give a generic response.
- The `general_agent.py` prompt already references a `brand_kb_search(query)` tool but it's not wired up to anything.

**What to embed:**
- `brand_name`, `brand_description`, `brand_short_pitch` — for general brand discovery
- `brand_additional_context` / FAQs — for specific questions (founders, materials, philosophy, pricing)
- Each brand gets chunked into the `brand_kb` collection with `brand_id` as metadata for filtering

**Two-phase fix:**

1. **Short term — inject brand summaries into `OneResideAgent` prompt**
   - Pass all brands' `brand_name` + `brand_short_pitch` + `categories_offered` into the One Reside agent prompt
   - Enough to answer "what is Kansso?" and guide user to scan QR for deeper exploration
   - No vector DB needed for this phase

2. **Proper fix — wire up `brand_kb_search` tool**
   - Create `brand_kb` Chroma collection, embed brand descriptions + FAQs per brand
   - Wire `brand_kb_search(query)` tool into `GeneralAgent` and `OneResideAgent`
   - Enables accurate answers to deep brand questions without hallucination

**Gap this closes:**

| User does | Handled by | Works now? | After fix? |
|---|---|---|---|
| Asks for products (no QR) | `ProductSearchAgent` (cross-brand) | ✅ | ✅ |
| Asks about One Reside platform | `OneResideAgent` | ✅ | ✅ |
| Asks about a specific brand (no QR) | `OneResideAgent` | ❌ no brand knowledge | ✅ |
| Asks deep brand FAQ (with QR) | `GeneralAgent` + `brand_kb_search` | ❌ tool not wired | ✅ |
