# ruff:noqa:E501
OPENAI_MODEL = "gpt-4o-mini"
GUPSHUP_SOURCE = "919594923839"
GUPSHUP_URL = "https://api.gupshup.io/wa/api/v1/msg"
EMBEDDING_MODEL = "text-embedding-3-small"
SKIP_FIELDS_LOGGER = (
    "args",
    "exc_info",
    "exc_text",
    "stack_info",
    "msg",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "name",
    "lineno",
    "funcName",
)

AWAZ_ROUTE = "https://api.awaz.ai/v1"
AWAZ_SOURCE = "+12315005708"
CALLCHIMP_ROUTE = "https://api.callchimp.ai/v1"

TEXT_EMBEDDING_MODEL = "text-embedding-3-small"

RAZORPAY_REDIRECT = "https://wa.me/919594923839"

ACK_MESSAGES = [
    "I will look into this immediately.",
    "I will take care of it.",
    "I'm working on that for you right now.",
    "Let me take care of this for you.",
    "I'm taking care of it as we speak.",
    "I'm taking care of everything for you.",
    "Leave it with me, I'm on it.",
]

UNSUPPORTED_TYPE_RESPONSES = [
    "I'm sorry, I'm currently unable to process images or voice recordings. Could you please share the details in text?",
    "I can't view that, but if you describe it, I'll help you right away \U0001f60a",
    "I can't access that, but just type it out and I'll take care of it.",
]
