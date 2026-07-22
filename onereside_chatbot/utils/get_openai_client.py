from openai import AsyncClient
from onereside_chatbot.utils.env_load import openai_api_key

openai_client = AsyncClient(api_key=openai_api_key)
