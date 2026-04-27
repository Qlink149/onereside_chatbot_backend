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
    "Certainly, allow me a moment to check this for you",
    "Noted, let me gather the relevant details for you.",
    "Of course, I'll look into this right away.",
    "Absolutely, allow me a moment to check this for you.",
    "Understood, I'll have this ready for you shortly",
]

AGENT_REQUEST_RESPONSES = [
    "Our concierge team has been notified and will connect with you shortly.\n\nIn the meantime, I'm here if you'd like to keep exploring — happy to help you find the right piece.",
    "Done — our team has been looped in and will reach out to you soon.\n\nFeel free to keep browsing in the meantime. I'm here if you need anything.",
    "I've let the team know — someone from One Reside will be in touch with you shortly.\n\nUntil then, happy to keep helping you explore.",
    "Our team's been notified and will connect with you soon.\n\nIn the meantime, let me know if there's anything else I can help you with.",
]

ENQUIRY_RESPONSES = [
    "Your enquiry has been noted — our team will reach out to you shortly with pricing and availability details for this piece.\n\nFeel free to keep exploring in the meantime.",
    "Got it! We've recorded your interest and someone from the One Reside team will be in touch soon with all the details.\n\nHappy to help you find more pieces while you wait.",
    "Enquiry received — our team will follow up with you shortly on pricing and next steps for this one.\n\nLet me know if there's anything else I can help you with.",
    "Noted! A member of our team will connect with you soon to share pricing and availability.\n\nIn the meantime, I'm here if you'd like to keep browsing.",
]

SUPPORT_NOTIFY_NUMBERS = [
    "918432563408",
    "917021863007"
    "918850070942"
]

UNSUPPORTED_TYPE_RESPONSES = [
    "I'm sorry, I'm currently unable to process images or voice recordings. Could you please share the details in text?",
    "I can't view that, but if you describe it, I'll help you right away 😊",
    "I can't access that, but just type it out and I'll take care of it.",
]
