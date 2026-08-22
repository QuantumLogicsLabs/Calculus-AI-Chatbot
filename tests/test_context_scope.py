"""
Objective 2: Determine the Scope of Context Loss
Author: Hamza Ali (Team Theta)

This test suite systematically checks the chatbot's context retention across:
1. 'Another example' requests
2. Clarification follow-ups
3. Topic switching
"""

import os
import sys
import json
import pytest

# Force the system to use MOCK mode so we don't hit real APIs during CI/CD
os.environ['USE_MOCK'] = 'True'

# Add the parent directory to sys.path to import the app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)
except ImportError:
    print("ℹ️ App not found in root. Adjust import path if running locally.")
    client = None


class TestContextScope:

    def setup_method(self):
        self.session_id = "test_session_001"
        self.conversation = []

    def send_message(self, message):
        payload = {
            "message": message,
            "session_id": self.session_id,
            "user_id": "test_user"
        }
        if client:
            response = client.post("/chat/stream", json=payload)
            return response.text
        else:
            print(f"📨 Sending: {message}")
            return f"Mock response for: {message}"

    def test_another_example_context(self):
        print("\n✅ Testing: Another Example Context")
        q1 = "What is the derivative of x^2?"
        r1 = self.send_message(q1)
        q2 = "Can you give me another example?"
        r2 = self.send_message(q2)
        assert "derivative" in r2.lower() or "d/dx" in r2.lower(), \
            "❌ Bot lost context! It didn't recognize 'derivative' topic."
        print("✅ Passed: Bot correctly generated another derivative example.")

    def test_clarification_context(self):
        print("\n✅ Testing: Clarification Context")
        q1 = "Explain gradient descent in simple terms."
        r1 = self.send_message(q1)
        q2 = "What is a learning rate in that context?"
        r2 = self.send_message(q2)
        assert "learning" in r2.lower() and "gradient" in r2.lower(), \
            "❌ Bot failed to connect 'learning rate' to 'gradient descent'."
        print("✅ Passed: Bot correctly linked clarification to previous topic.")

    def test_cross_topic_mixing(self):
        print("\n✅ Testing: Cross-Topic Mixing")
        q1 = "Find the integral of 2x."
        r1 = self.send_message(q1)
        q2 = "Now find the derivative of that."
        r2 = self.send_message(q2)
        assert "derivative" in r2.lower() or "d/dx" in r2.lower(), \
            "❌ Bot confused the operation! It didn't switch to derivative."
        print("✅ Passed: Bot correctly switched operations.")

    def test_known_context_loss_scenario(self):
        print("\n✅ Testing: Known Failure Scope")
        q1 = "What is a vector?"
        r1 = self.send_message(q1)
        q2 = "Give me a practical example."
        r2 = self.send_message(q2)
        assert "vector" in r2.lower() or "direction" in r2.lower(), \
            "⚠️ Expected behavior: Bot might lose context here."
        print(f"ℹ️ Response received: {r2[:50]}...")

print("\n🎉 Context Scope Tests Ready!")
