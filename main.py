"""Vercel entrypoint — re-exports the FastAPI app."""

from onereside_chatbot.main import app

__all__ = ["app"]
