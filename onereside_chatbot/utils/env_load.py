import os

from dotenv import load_dotenv

load_dotenv()

openai_api_key = os.environ.get("OPENAI_API_KEY")
mongo_uri = os.environ.get("MONGO_URI")
# Application Mongo database name. MONGO_DB_NAME overrides MONGO_PROD_DB_NAME (e2e/local test DB).
mongo_prod_db_name = (
    os.environ.get("MONGO_DB_NAME")
    or os.environ.get("MONGO_PROD_DB_NAME")
    or "OneReside"
)
# Dedicated DB for pytest. Required by characterisation/identity isolation fixtures.
mongo_test_db_name = os.environ.get("MONGO_TEST_DB_NAME", "")
gupshup_app_id = os.environ.get("GUPSHUP_APP_ID")
gupshup_token = os.environ.get("GUPSHUP_TOKEN")
gupshup_app_name = os.environ.get("GUPSHUP_APP_NAME")
gupshup_api_key = os.environ.get("GUPSHUP_API_KEY")
pinecone_api = os.environ.get("PINECONE_API")
pinecone_namespace = os.environ.get("PINECONE_NAMESPACE")
webhook_api = os.environ.get("WEBHOOK_API")

google_private_key_id = os.environ.get("GOOGLE_PRIVATE_KEY_ID")

qlink_app_id = os.environ.get("QLINK_APP_ID")
qlink_app_name = os.environ.get("QLINK_APP_NAME")
qlink_token = os.environ.get("QLINK_TOKEN")

username = os.environ.get("LOGIN_USERNAME")
password = os.environ.get("LOGIN_PASS")
dashboard_api_key = os.environ.get("DASHBOARD_API_KEY")
is_production = os.environ.get("ENV_MODE", "dev") == "prod"
jwt_secret = os.environ.get("JWT_SECRET")
jwt_expire_minutes = int(os.environ.get("JWT_EXPIRE_MINUTES", "480"))

futwork_webhook = os.environ.get("FUTWORKS_API")
futwork_pacific_agent = os.environ.get("FUTWORK_PACIFIC_AGENT")


chroma_api = os.getenv("CHROMA_API_KEY")
chorma_tenant = os.getenv("CHROMA_TENANT")

razorpay_webhook_secrete = os.getenv("RAZORPAY_WEBHOOK_SECRET")
razorpay_app_id = os.getenv("RAZORPAY_APP_ID")
razorpay_app_secrete = os.getenv("RAZORPAY_APP_SECRETE")

r2_access_key = os.getenv("R2_ACCESS_KEY")
r2_secret_key = os.getenv("R2_SECRET_KEY")
r2_endpoint = os.getenv("R2_ENDPOINT")
r2_bucket = os.getenv("R2_BUCKET")
r2_public_url = os.getenv("R2_PUBLIC_URL")

web_success_url = os.getenv("WEB_SUCCESS_URL", "https://onereside.com")

_DEFAULT_WEB_ALLOWED_ORIGINS = "https://onereside.com"


def parse_web_allowed_origins(raw: str | None) -> list[str]:
    """Comma-separated browser origins (scheme + host + port, no path)."""
    value = (raw or "").strip() or _DEFAULT_WEB_ALLOWED_ORIGINS
    return [part.strip().rstrip("/") for part in value.split(",") if part.strip()]


web_allowed_origins = parse_web_allowed_origins(os.getenv("WEB_ALLOWED_ORIGINS"))
