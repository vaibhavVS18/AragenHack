"""Provider-agnostic interface for the Explain step.

Keeps Gemini swappable for Claude/Ollama/mock without touching the agent.

TODO(step 4): class LLMProvider(Protocol): async def explain(batch) -> list[Explanation]
"""
