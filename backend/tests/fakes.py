"""FakeLLM: plays back scripted replies and records every input, so tests run offline."""
from __future__ import annotations

import copy
import json

from weekfeed.llm import LLMResult, ToolCall


class FakeLLM:
    def __init__(self, script: list[LLMResult | Exception] | None = None):
        self.script = list(script or [])
        self.calls: list[dict] = []

    def add(self, *results: LLMResult | Exception) -> FakeLLM:
        self.script.extend(results)
        return self

    def respond(self, input, *, instructions, tools=None, output_schema=None, schema_name="output"):
        self.calls.append({
            "input": copy.deepcopy(input), "instructions": instructions, "tools": tools,
            "output_schema": output_schema, "schema_name": schema_name,
        })
        if not self.script:
            raise AssertionError("FakeLLM script exhausted")
        nxt = self.script.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    def prompt_text(self, call_index: int = -1) -> str:
        """Everything sent in one call, flattened to text, for 'was X in the prompt' assertions."""
        return json.dumps(self.calls[call_index]["input"])


def reply(text: str) -> LLMResult:
    return LLMResult(text=text, output_items=[{"role": "assistant", "content": text}])


def tool_calls(*calls: tuple[str, dict]) -> LLMResult:
    tcs = [ToolCall(call_id=f"call_{i}_{name}", name=name, arguments=args) for i, (name, args) in enumerate(calls)]
    items = [{"type": "function_call", "call_id": t.call_id, "name": t.name, "arguments": json.dumps(t.arguments)} for t in tcs]
    return LLMResult(tool_calls=tcs, output_items=items)


def structured(obj: dict) -> LLMResult:
    return LLMResult(text=json.dumps(obj), parsed=obj)
