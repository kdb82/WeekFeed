"""The only code that talks to OpenAI (Responses API)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

import openai

from .config import Config


class LLMError(Exception):
    pass


class AIDisabled(LLMError):
    """No API key/model configured -> 503."""


class LLMUnavailable(LLMError):
    """Rate limit, 5xx, timeout or connection error after the SDK's retries -> 502."""


class LLMAuthError(LLMError):
    """OpenAI rejected the API key -> 502."""


class LLMBadOutput(LLMError):
    """Structured output that wasn't valid JSON -> 502."""


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict


@dataclass
class LLMResult:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    # Items to append to the next request's input so the model sees its own tool calls.
    output_items: list[dict] = field(default_factory=list)
    parsed: Any = None


class LLM(Protocol):
    def respond(
        self,
        input: list[dict],
        *,
        instructions: str,
        tools: list[dict] | None = None,
        output_schema: dict | None = None,
        schema_name: str = "output",
    ) -> LLMResult: ...


def function_tool(name: str, description: str, properties: dict) -> dict:
    """A strict function tool. Strict mode requires every property; optional ones use a null type."""
    return {
        "type": "function",
        "name": name,
        "description": description,
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        },
    }


class OpenAILLM:
    def __init__(self, api_key: str, model: str, client: Any = None):
        self.model = model
        self.client = client or openai.OpenAI(api_key=api_key, max_retries=2, timeout=60.0)

    def respond(self, input, *, instructions, tools=None, output_schema=None, schema_name="output") -> LLMResult:
        kwargs: dict[str, Any] = {"model": self.model, "input": input, "instructions": instructions}
        if tools:
            kwargs["tools"] = tools
        if output_schema is not None:
            kwargs["text"] = {
                "format": {"type": "json_schema", "name": schema_name, "schema": output_schema, "strict": True}
            }
        try:
            resp = self.client.responses.create(**kwargs)
        except openai.AuthenticationError as e:
            raise LLMAuthError("OpenAI rejected the API key. Check OPENAI_API_KEY in .env.") from e
        except openai.APIStatusError as e:
            raise LLMUnavailable(f"OpenAI returned an error ({e.status_code})") from e
        except openai.APIConnectionError as e:  # includes timeouts
            raise LLMUnavailable("Couldn't reach OpenAI") from e

        calls: list[ToolCall] = []
        items: list[dict] = []
        for item in resp.output:
            if getattr(item, "type", None) == "function_call":
                calls.append(ToolCall(item.call_id, item.name, json.loads(item.arguments or "{}")))
                # Echo a minimal function_call item (no server ids), so no server-side state is needed.
                items.append({"type": "function_call", "call_id": item.call_id, "name": item.name, "arguments": item.arguments})
        text = resp.output_text or ""
        if text:
            items.append({"role": "assistant", "content": text})

        parsed = None
        if output_schema is not None and not calls:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as e:
                raise LLMBadOutput(f"Model returned invalid JSON: {e}") from e
        return LLMResult(text=text, tool_calls=calls, output_items=items, parsed=parsed)


def respond_json(llm: LLM, input: list[dict], *, instructions: str, schema: dict, schema_name: str) -> dict:
    """Structured call with one retry that tells the model what was wrong."""
    error = "no JSON returned"
    for attempt in range(2):
        messages = input if attempt == 0 else [
            *input, {"role": "user", "content": f"Your previous reply was not valid JSON ({error}). Reply again with valid JSON only."}
        ]
        try:
            result = llm.respond(messages, instructions=instructions, output_schema=schema, schema_name=schema_name)
        except LLMBadOutput as e:
            error = str(e)
            continue
        if isinstance(result.parsed, dict):
            return result.parsed
        try:
            value = json.loads(result.text)
            if isinstance(value, dict):
                return value
            error = "expected a JSON object"
        except json.JSONDecodeError as e:
            error = str(e)
    raise LLMBadOutput(f"Model returned invalid JSON twice: {error}")


def make_llm(config: Config) -> LLM | None:
    if not config.ai_enabled:
        return None
    return OpenAILLM(config.openai_api_key, config.openai_model)  # type: ignore[arg-type]
