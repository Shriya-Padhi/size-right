"""Tests the function-calling loop with a scripted fake model (no network)."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import SYSTEM_PROMPT, run_tool, run_turn  # noqa: E402


class FakeClient:
    """Mimics client.chat.completions.create(): first a tool call, then a text answer."""

    def __init__(self, tool_args):
        self.tool_args = tool_args
        self.calls = 0
        self.chat = NS(completions=NS(create=self.create))

    def create(self, model, messages, tools):
        self.calls += 1
        if self.calls == 1:
            call = NS(id="call_1",
                      function=NS(name="size_heat_pump", arguments=json.dumps(self.tool_args)))
            return NS(choices=[NS(message=NS(content=None, tool_calls=[call]))])
        result = json.loads(messages[-1]["content"])
        tons = result["recommendation"]["nominal_tons"]
        return NS(choices=[NS(message=NS(content=f"Recommended: {tons} tons.", tool_calls=None))])


def test_loop_runs_tool_then_answers():
    client = FakeClient({"floor_area_ft2": 1400, "insulation": "poor",
                         "air_tightness": "leaky", "city": "Minneapolis, MN"})
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": "Drafty 1950s ranch in Minneapolis, 1,400 sq ft"}]
    reply, events = run_turn(client, "fake", messages)

    assert reply == "Recommended: 5.0 tons."
    assert events[0]["tool"] == "size_heat_pump"
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "tool", "assistant"]


def test_tool_errors_return_as_data():
    out = run_tool("size_heat_pump", {"floor_area_ft2": 1500, "insulation": "average",
                                      "air_tightness": "average", "city": "Atlantis"})
    assert "error" in out
    assert "error" in run_tool("nope", {})