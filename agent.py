"""Function-calling agent: the LLM gathers facts, our code does the math."""

from __future__ import annotations

import json
import os

from sizing import Home, load_cities, size_home

SYSTEM_PROMPT = """You are SizeRight, a friendly assistant that estimates heat pump size for a home.

Gather these facts conversationally, asking at most two questions at a time:
- city (or the local winter and summer design temperatures)
- conditioned floor area in square feet and number of stories
- insulation level: poor (older, little insulation), average, or good (recent, well insulated)
- air tightness: leaky (drafty), average, or tight
Optional: ceiling height (default 8 ft), share of wall that is windows (default 0.15), occupants (default 3).

Infer levels from descriptions (a "drafty 1950s ranch" is leaky with poor insulation) and say what you assumed.
Never calculate loads yourself. Call `size_heat_pump` once you have the required facts, and call
`list_cities` if the city may not be supported. Then explain the result in plain words: heating and
cooling load, recommended size in tons, backup heat, and the balance point. Always end with the
disclaimer that this is an educational estimate, not a Manual J."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "size_heat_pump",
            "description": "Estimate design heating/cooling loads and recommend a nominal heat pump size.",
            "parameters": {
                "type": "object",
                "properties": {
                    "floor_area_ft2": {"type": "number", "description": "Conditioned floor area in square feet"},
                    "stories": {"type": "integer", "default": 1},
                    "ceiling_height_ft": {"type": "number", "default": 8},
                    "insulation": {"type": "string", "enum": ["poor", "average", "good"]},
                    "air_tightness": {"type": "string", "enum": ["leaky", "average", "tight"]},
                    "window_fraction": {"type": "number", "default": 0.15},
                    "occupants": {"type": "integer", "default": 3},
                    "city": {"type": "string", "description": "City and state, e.g. 'Minneapolis, MN'"},
                    "heating_design_f": {"type": "number", "description": "Use only if no city"},
                    "cooling_design_f": {"type": "number", "description": "Use only if no city"},
                },
                "required": ["floor_area_ft2", "insulation", "air_tightness"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_cities",
            "description": "List cities with built-in design temperature data.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

HOME_FIELDS = {"floor_area_ft2", "stories", "ceiling_height_ft", "insulation",
               "air_tightness", "window_fraction", "occupants"}


def run_tool(name: str, args: dict) -> dict:
    """Execute a tool call. Errors go back to the model as data so it can recover."""
    try:
        if name == "list_cities":
            return {"cities": sorted(row["city"] for row in load_cities().values())}
        if name == "size_heat_pump":
            home = Home(**{k: v for k, v in args.items() if k in HOME_FIELDS})
            return size_home(
                home,
                city=args.get("city"),
                heating_design_f=args.get("heating_design_f"),
                cooling_design_f=args.get("cooling_design_f"),
            )
        return {"error": f"Unknown tool {name}"}
    except (ValueError, TypeError) as exc:
        return {"error": str(exc)}


def make_client():
    """OpenAI-compatible client. Defaults to a local Ollama server."""
    from openai import OpenAI

    return OpenAI(
        base_url=os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"),
        api_key=os.getenv("LLM_API_KEY", "ollama"),
    )


def model_name() -> str:
    return os.getenv("LLM_MODEL", "qwen2.5:7b")


def run_turn(client, model: str, messages: list[dict], max_rounds: int = 5) -> tuple[str, list[dict]]:
    """Send messages, execute any tool calls, repeat until the model answers in text.

    Mutates `messages` so the conversation keeps its history.
    Returns (reply_text, tool_events) where tool_events lists each tool call and its result.
    """
    events = []
    for _ in range(max_rounds):
        resp = client.chat.completions.create(model=model, messages=messages, tools=TOOLS)
        msg = resp.choices[0].message

        # Case A: plain text answer -> done
        if not msg.tool_calls:
            messages.append({"role": "assistant", "content": msg.content or ""})
            return msg.content or "", events

        # Case B: the model asked for tools. Record its request in the history.
        messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ],
        })

        # Run each requested tool and send the result back, linked by tool_call_id
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = run_tool(tc.function.name, args)
            events.append({"tool": tc.function.name, "args": args, "result": result})
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)})

    return "I couldn't finish that calculation. Could you rephrase?", events