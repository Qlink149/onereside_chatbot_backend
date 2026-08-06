from dataclasses import dataclass, field
from typing import Literal

@dataclass
class Turn:
    channel: Literal["whatsapp", "web"]
    user_ref: str          # phone for WhatsApp, "web:<uuid>" for web
    session_id: str | None
    messages: dict         # exactly the shape data["messages"] already uses
    display_name: str
    received_at: int
    metadata: dict = field(default_factory=dict)
