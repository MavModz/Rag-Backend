"""Model Gateway.

The single chokepoint through which every agent reaches an LLM. Agents request a
*profile* (e.g. ``conversation.default``) and never name a concrete provider, so
routing, retry, fallback, cost optimization and usage tracking all live here. M1
wires only local Ollama behind it; Gemini/Claude/OpenAI slot in later with no
caller changes.
"""
