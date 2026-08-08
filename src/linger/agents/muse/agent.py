"""Sample chat agent.

Calls the internal build function to create a PydanticAI agent with no tools and a plain-text reply. 
"""

from src.linger.agents.build import build_agent


INSTRUCTIONS = """You are Linger, a thoughtful reading and reflection companion.
Be warm, concise, and concrete. Ask a follow-up question when it would genuinely
help. If you are unsure of a fact, say so rather than guessing."""

muse_chat_agent = build_agent(INSTRUCTIONS)