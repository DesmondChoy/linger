"""Request bodies for the chat API.

Replies are streamed as server-sent events rather than returned as a model,
so there is no response body to declare here.
"""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=8000)
