"""
llm_gateway.py — Unified LLM access layer supporting Gemini, Groq, and Ollama.

Config is read from env vars on each call so you can hot-swap providers
without restarting the server. If LLM_API_KEY is empty or the call fails,
callers should fall back to rule-based strategies.
"""

import os
import json
import logging
import httpx

logger = logging.getLogger("stockpulse.llm_gateway")

# Timeout for LLM calls — 15s is generous for flash models
LLM_TIMEOUT = 15.0


def call_llm(prompt: str) -> str:
    """
    Send a prompt to the configured LLM provider and return the raw text response.

    Reads LLM_PROVIDER, LLM_API_KEY, LLM_MODEL, LLM_BASE_URL from env vars
    fresh on every call. Raises on failure so callers can catch and fall back.

    Supports three providers:
    - gemini: Google Generative Language API (REST, non-OpenAI format)
    - groq: OpenAI-compatible chat completions
    - ollama: Local OpenAI-compatible chat completions (no API key needed)
    """
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()
    api_key = os.getenv("LLM_API_KEY", "")
    model = os.getenv("LLM_MODEL", "gemini-1.5-flash")
    base_url = os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com")

    if not api_key and provider != "ollama":
        raise ValueError("LLM_API_KEY is not set — falling back to rule-based strategy")

    if provider == "gemini":
        return _call_gemini(prompt, api_key, model, base_url)
    elif provider == "groq":
        return _call_openai_compatible(prompt, api_key, model, base_url or "https://api.groq.com/openai/v1")
    elif provider == "ollama":
        return _call_openai_compatible(prompt, "", model, base_url or "http://localhost:11434/v1")
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {provider}")


def _call_gemini(prompt: str, api_key: str, model: str, base_url: str) -> str:
    """
    Call Google Gemini via the REST generateContent endpoint.
    Returns the text content from the first candidate.
    """
    url = f"{base_url}/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 512},
    }
    resp = httpx.post(url, json=payload, timeout=LLM_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _call_openai_compatible(prompt: str, api_key: str, model: str, base_url: str) -> str:
    """
    Call any OpenAI-compatible endpoint (Groq, Ollama, etc.).
    Returns the assistant message content from the chat completions response.
    """
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a commerce pricing and inventory advisor. Respond with strict JSON only, no markdown."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 512,
    }
    resp = httpx.post(url, json=payload, headers=headers, timeout=LLM_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]
