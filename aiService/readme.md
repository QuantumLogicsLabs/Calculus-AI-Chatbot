# CalcVoyager Chat Service

## Run

uvicorn aiService.chatbot:app --reload

## Endpoints

GET /

GET /health

POST /chat

## Example Request

{
  "message": "Find derivative of x^2",
  "topic": "derivatives",
  "history": []
}


## Example Response

{
  "answer": "..."
}