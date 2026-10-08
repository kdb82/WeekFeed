from types import SimpleNamespace

import httpx
import openai
import pytest

from tests.fakes import FakeLLM, structured
from weekfeed.config import Config
from weekfeed.llm import (
    LLMAuthError, LLMBadOutput, LLMResult, LLMUnavailable, OpenAILLM, function_tool, make_llm, respond_json,
)

REQUEST = httpx.Request("POST", "https://api.openai.com/v1/responses")


class FakeResponses:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.kwargs = response, error, None

    def create(self, **kwargs):
        self.kwargs = kwargs
        if self.error:
            raise self.error
        return self.response


def client_with(response=None, error=None):
    return SimpleNamespace(responses=FakeResponses(response, error))


def test_function_tool_is_strict_and_requires_every_property():
    tool = function_tool("add_todo", "Add a todo", {"text": {"type": "string"}, "project": {"type": ["string", "null"]}})
    assert tool["strict"] is True
    assert tool["parameters"]["required"] == ["text", "project"]
    assert tool["parameters"]["additionalProperties"] is False


def test_openai_llm_parses_tool_calls_and_echo_items():
    response = SimpleNamespace(
        output=[SimpleNamespace(type="function_call", call_id="c1", name="add_todo", arguments='{"text": "x"}')],
        output_text="",
    )
    client = client_with(response)
    result = OpenAILLM("sk", "model-x", client=client).respond(
        [{"role": "user", "content": "hi"}], instructions="rules", tools=[{"type": "function"}]
    )
    assert [(c.call_id, c.name, c.arguments) for c in result.tool_calls] == [("c1", "add_todo", {"text": "x"})]
    assert result.output_items == [{"type": "function_call", "call_id": "c1", "name": "add_todo", "arguments": '{"text": "x"}'}]
    assert client.responses.kwargs["model"] == "model-x"
    assert client.responses.kwargs["instructions"] == "rules"


def test_openai_llm_structured_output():
    response = SimpleNamespace(output=[SimpleNamespace(type="message")], output_text='{"terms": ["a"]}')
    client = client_with(response)
    result = OpenAILLM("sk", "m", client=client).respond([], instructions="", output_schema={"type": "object"}, schema_name="t")
    assert result.parsed == {"terms": ["a"]}
    assert client.responses.kwargs["text"]["format"]["type"] == "json_schema"
    assert client.responses.kwargs["text"]["format"]["strict"] is True


def test_openai_llm_bad_json_raises_bad_output():
    response = SimpleNamespace(output=[], output_text="not json")
    with pytest.raises(LLMBadOutput):
        OpenAILLM("sk", "m", client=client_with(response)).respond([], instructions="", output_schema={"type": "object"})


def test_openai_llm_maps_errors():
    auth = openai.AuthenticationError("bad key", response=httpx.Response(401, request=REQUEST), body=None)
    with pytest.raises(LLMAuthError):
        OpenAILLM("sk", "m", client=client_with(error=auth)).respond([], instructions="")
    conn_err = openai.APIConnectionError(request=REQUEST)
    with pytest.raises(LLMUnavailable):
        OpenAILLM("sk", "m", client=client_with(error=conn_err)).respond([], instructions="")
    rate = openai.RateLimitError("slow down", response=httpx.Response(429, request=REQUEST), body=None)
    with pytest.raises(LLMUnavailable):
        OpenAILLM("sk", "m", client=client_with(error=rate)).respond([], instructions="")


def test_respond_json_retries_once_with_the_error():
    llm = FakeLLM([LLMResult(text="nope"), structured({"ok": True})])
    assert respond_json(llm, [{"role": "user", "content": "q"}], instructions="", schema={}, schema_name="s") == {"ok": True}
    assert "valid JSON" in llm.prompt_text(1)


def test_respond_json_gives_up_after_second_failure():
    llm = FakeLLM([LLMResult(text="nope"), LLMResult(text="still nope")])
    with pytest.raises(LLMBadOutput):
        respond_json(llm, [], instructions="", schema={}, schema_name="s")


def test_make_llm_needs_key_and_model(tmp_path):
    assert make_llm(Config(None, None, tmp_path / "x.db", 1)) is None
    assert isinstance(make_llm(Config("sk", "m", tmp_path / "x.db", 1)), OpenAILLM)
