import os
import time
import json
import logging
import asyncio
import re
import string
from typing import Optional, List

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from app.graph import app, georgianize_digits_for_tts  # your compiled LangGraph
from dotenv import load_dotenv

# -----------------------------
# Env
# -----------------------------
load_dotenv()

# Fail-fast if missing (demo-safe)
public_key = os.environ["VAPI_PUBLIC_KEY"]
assistant_id = os.environ["VAPI_ASSISTANT_ID"]

COMPANY_NAME = os.getenv("COMPANY_NAME", "კომპანია").strip() or "კომპანია"
END_PHRASE = f"დიდი მადლობა ზარისთვის {COMPANY_NAME}-ში ნახვამდის!"

# -----------------------------
# Logging
# -----------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("LeadFlow")

# -----------------------------
# App
# -----------------------------
app_server = FastAPI()

# CORS (local dev defaults)
app_server.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app_server.get("/health")
def health():
    return {"ok": True}

@app_server.get("/vapi-config")
def vapi_config():
    # Single source of truth
    return JSONResponse({"publicKey": public_key, "assistantId": assistant_id})

# -----------------------------
# Helpers
# -----------------------------
def to_lc_message(m: dict) -> Optional[BaseMessage]:
    role = m.get("role")
    content = (m.get("content") or "").strip()
    if not content:
        return None

    if role == "user":
        return HumanMessage(content=content)
    if role == "assistant":
        return AIMessage(content=content)

    # ignore system/other roles to avoid duplicating system prompt
    return None


def get_thread_id(data: dict) -> str:
    return (
        str(data.get("conversation_id"))
        or str(data.get("call_id"))
        or str(data.get("session_id"))
        or str(int(time.time() * 1000))
    )


def _normalize_for_match(s: str) -> str:
    """
    Make end-call detection robust:
    - lowercase
    - remove punctuation
    - collapse whitespace
    """
    if not s:
        return ""
    s = s.lower()
    s = s.translate(str.maketrans("", "", string.punctuation))
    s = re.sub(r"\s+", " ", s).strip()
    return s


def should_end_call(final_response: str) -> bool:
    fr = _normalize_for_match(final_response)

    # Accept a few common variants (punctuation/spaces differ)
    variants = [
        END_PHRASE,
        f"დიდი მადლობა ზარისთვის {COMPANY_NAME}-ში. ნახვამდის!",
        f"დიდი მადლობა ზარისთვის {COMPANY_NAME}-ში ნახვამდის!",
        f"დიდი მადლობა ზარისთვის {COMPANY_NAME} ნახვამდის!",
    ]
    return any(_normalize_for_match(v) in fr for v in variants)

# -----------------------------
# Streaming generator
# -----------------------------
async def stream_generator(history: List[BaseMessage], thread_id: str):
    chunk_id = f"chatcmpl-{int(time.time())}"
    created = int(time.time())

    # --- STEP 1: INSTANT ACK ---
    yield (
        "data: "
        + json.dumps(
            {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": "leadflow-v1",
                "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
            }
        )
        + "\n\n"
    )

    try:
        # --- STEP 2: RUN THE BRAIN with FULL HISTORY ---
        config = {"configurable": {"thread_id": thread_id}}

        events = await asyncio.to_thread(
            lambda: list(
                app.stream(
                    {"messages": history},
                    config=config,
                    stream_mode="values",
                )
            )
        )

        final_response = events[-1]["messages"][-1].content or ""
        spoken_response = georgianize_digits_for_tts(final_response)
        logger.info(f"🗣️ Brain Said: {final_response}")

        # --- STEP 3: SEND CONTENT ---
        yield (
            "data: "
            + json.dumps(
                {
                    "id": chunk_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": "leadflow-v1",
                    "choices": [
                        {"index": 0, "delta": {"content": spoken_response}, "finish_reason": None}
                    ],
                }
            )
            + "\n\n"
        )

        # Decide whether we should end the call
        if should_end_call(final_response):
            await asyncio.sleep(0.8)  # allow TTS to start speaking

            tool_call_id = f"call_{int(time.time() * 1000)}"
            yield (
                "data: "
                + json.dumps(
                    {
                        "id": chunk_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": "leadflow-v1",
                        "choices": [
                            {
                                "index": 0,
                                "delta": {
                                    "tool_calls": [
                                        {
                                            "index": 0,
                                            "id": tool_call_id,
                                            "type": "function",
                                            "function": {"name": "endCall", "arguments": "{}"},
                                        }
                                    ]
                                },
                                "finish_reason": "tool_calls",
                            }
                        ],
                    }
                )
                + "\n\n"
            )

    except Exception as e:
        logger.exception("Streaming error")
        # Send a safe fallback message so the client isn't left hanging
        yield (
            "data: "
            + json.dumps(
                {
                    "id": chunk_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": "leadflow-v1",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": "ბოდიში, ტექნიკური პრობლემა მაქვს. სცადეთ თავიდან."},
                            "finish_reason": None,
                        }
                    ],
                }
            )
            + "\n\n"
        )

    # --- CLOSE STREAM ---
    yield (
        "data: "
        + json.dumps(
            {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": "leadflow-v1",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
        )
        + "\n\n"
    )
    yield "data: [DONE]\n\n"


# -----------------------------
# Endpoint
# -----------------------------
@app_server.post("/chat/completions")
async def chat_endpoint(request: Request):
    data = await request.json()
    raw_messages = data.get("messages", [])

    history = [to_lc_message(m) for m in raw_messages]
    history = [m for m in history if m is not None]

    if not history:
        history = [HumanMessage(content="Hello")]

    last_user = next((m for m in reversed(raw_messages) if m.get("role") == "user"), None)
    logger.info(f"📞 Brain Heard: {(last_user or {}).get('content', 'Hello')}")

    thread_id = get_thread_id(data)

    return StreamingResponse(stream_generator(history, thread_id), media_type="text/event-stream")


if __name__ == "__main__":
    uvicorn.run(app_server, host="0.0.0.0", port=8000)
