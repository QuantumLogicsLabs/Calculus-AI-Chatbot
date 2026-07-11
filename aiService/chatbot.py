from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import logging
import re
import json

from aiService.services.llm_client import ask_llm, ask_llm_stream

# Configure logging
logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="CalcVoyager Chat Service",
    description="Backend API service for the CalcVoyager AI chatbot",
    version="1.0.0"
)


class ChatRequest(BaseModel):
    message: str
    topic: str = ""
    difficulty: str = "intermediate"  # CB-18: beginner | intermediate | advanced
    history: list = Field(default_factory=list)

class ChatResponse(BaseModel):
    answer: str
    suggestions: list[str] = Field(default_factory=list)


def parse_follow_ups(raw_response: str) -> tuple[str, list[str]]:
    """
    Extract [FOLLOW_UPS]...[/FOLLOW_UPS] block from LLM response.

    Returns:
        (clean_answer, suggestions_list)
    """
    pattern = r'\[FOLLOW_UPS\](.*?)\[/FOLLOW_UPS\]'
    match = re.search(pattern, raw_response, re.DOTALL | re.IGNORECASE)

    if not match:
        return raw_response.strip(), []

    follow_ups_text = match.group(1).strip()
    clean_answer = re.sub(pattern, '', raw_response, flags=re.DOTALL | re.IGNORECASE).strip()

    suggestions = []
    for line in follow_ups_text.split('\n'):
        line = line.strip()
        if not line:
            continue
        cleaned = re.sub(r'^\d+[\.\)]\s*', '', line)
        cleaned = re.sub(r'^-\s*', '', cleaned)
        if cleaned:
            suggestions.append(cleaned)

    return clean_answer, suggestions


@app.get("/")
async def home():
    return {
        "status": "running",
        "service": "CalcVoyager Chat Service"
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy"
    }

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):

    try:
        logging.info(
            f"Received question: {request.message} (difficulty={request.difficulty})"
        )

        raw_response = await ask_llm(
            message=request.message,
            topic=request.topic,
            history=request.history,
            difficulty=request.difficulty
        )

        clean_answer, suggestions = parse_follow_ups(raw_response)

        logging.info(
            f"Parsed {len(suggestions)} follow-up suggestions"
        )

        return ChatResponse(
            answer=clean_answer,
            suggestions=suggestions
        )

    except Exception as e:
        logging.error(
            f"Chat error: {str(e)}"
        )
        raise HTTPException(
            status_code=500,
            detail="AI service unavailable"
        )


class ChatStreamRequest(BaseModel):
    message: str
    topic: str = ""
    difficulty: str = "intermediate"  # CB-18
    history: list = Field(default_factory=list)


@app.post("/chat/stream")
async def chat_stream(request: ChatStreamRequest):
    """
    Streaming chat endpoint. Sends Server-Sent Events (SSE) as the
    model generates tokens, instead of waiting for the full response.

    Event format:
        data: <json with a "token" field>\n\n
    Final event:
        data: [DONE]\n\n
    On error:
        data: <json with an "error" field>\n\n   followed by [DONE]
    """

    async def event_generator():
        full_response = ""
        try:
            logging.info(
                f"Received streaming question: {request.message} (difficulty={request.difficulty})"
            )

            async for token in ask_llm_stream(
                message=request.message,
                topic=request.topic,
                history=request.history,
                difficulty=request.difficulty
            ):
                full_response += token
                payload = json.dumps({"token": token})
                yield f"data: {payload}\n\n"

            # Once streaming is done, parse follow-ups from the
            # full concatenated text and send them as a final event
            clean_answer, suggestions = parse_follow_ups(full_response)
            final_payload = json.dumps({
                "done": True,
                "suggestions": suggestions
            })
            yield f"data: {final_payload}\n\n"

        except Exception as e:
            logging.error(
                f"Streaming chat error: {str(e)}"
            )
            error_payload = json.dumps({"error": "AI service unavailable"})
            yield f"data: {error_payload}\n\n"

        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disables proxy buffering (e.g. nginx)
        }
    )