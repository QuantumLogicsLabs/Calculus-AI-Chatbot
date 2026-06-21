from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import logging
import re

from aiService.services.llm_client import ask_llm

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
    # Pattern to match [FOLLOW_UPS]...[/FOLLOW_UPS] block
    pattern = r'\[FOLLOW_UPS\](.*?)\[/FOLLOW_UPS\]'
    match = re.search(pattern, raw_response, re.DOTALL | re.IGNORECASE)
    
    if not match:
        # No follow-ups found, return original response with empty list
        return raw_response.strip(), []
    
    # Extract the follow-ups text
    follow_ups_text = match.group(1).strip()
    
    # Remove the [FOLLOW_UPS] block from the main answer
    clean_answer = re.sub(pattern, '', raw_response, flags=re.DOTALL | re.IGNORECASE).strip()
    
    # Parse numbered list (e.g., "1. Question here\n2. Another question")
    suggestions = []
    for line in follow_ups_text.split('\n'):
        line = line.strip()
        if not line:
            continue
        # Match patterns like "1. ", "2)", "3 -", etc.
        cleaned = re.sub(r'^\d+[\.\)]\s*', '', line)
        cleaned = re.sub(r'^-\s*', '', cleaned)  # Also handle "- Question"
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
            f"Received question: {request.message}"
        )

        raw_response = await ask_llm(
            message=request.message,
            topic=request.topic,
            history=request.history
        )

        # Parse out the [FOLLOW_UPS] block
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