"""Chainlit UI for SizeRight. Run with: chainlit run app.py -w"""

import json

import chainlit as cl
from dotenv import load_dotenv

from agent import SYSTEM_PROMPT, make_client, model_name, run_turn

load_dotenv()

STARTERS = [
    ("Drafty 1950s ranch", "I have a drafty 1950s ranch in Minneapolis, about 1,400 square feet."),
    ("New build in Denver", "New, well insulated two-story home in Denver, 2,400 sq ft, pretty airtight."),
    ("Boston colonial", "1920s colonial in Boston, 2,000 square feet over two floors, some insulation added."),
]


@cl.set_starters
async def starters():
    return [cl.Starter(label=label, message=msg) for label, msg in STARTERS]


@cl.on_chat_start
async def start():
    cl.user_session.set("messages", [{"role": "system", "content": SYSTEM_PROMPT}])
    cl.user_session.set("client", make_client())


@cl.on_message
async def on_message(message: cl.Message):
    messages = cl.user_session.get("messages")
    messages.append({"role": "user", "content": message.content})
    try:
        reply, events = await cl.make_async(run_turn)(
            cl.user_session.get("client"), model_name(), messages
        )
    except Exception as exc:  # connection or model errors
        await cl.Message(
            content=f"Couldn't reach the language model: {exc}. "
                    "Check LLM_BASE_URL and LLM_MODEL in .env."
        ).send()
        return

    for ev in events:
        async with cl.Step(name=ev["tool"], type="tool") as step:
            step.input = json.dumps(ev["args"], indent=2)
            step.output = json.dumps(ev["result"], indent=2)

    await cl.Message(content=reply).send()