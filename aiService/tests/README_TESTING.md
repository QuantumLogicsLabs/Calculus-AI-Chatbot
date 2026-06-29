# CalcVoyager Test Suite - Quick Start Guide

## Running the Tests

# 1. Set USE_MOCK = False in llm_client.py
# 2. Make sure GROK_API_KEY is set in aiService/services/.env
# 3. From the project root:

python -m aiService.tests.chatbot_tests
### 1. Prerequisites

Before running tests, ensure:

```bash
# 1. Install dependencies
pip install -r aiService/requirements.txt

# 2. Configure environment
# Edit aiService/services/.env and add:
GROK_API_KEY=xai-your-actual-key-here

# 3. Enable real API testing
# Edit aiService/services/llm_client.py line 12:
USE_MOCK = False  # Change from True to False
```

### 2. Execute All Tests

From the project root directory:

```bash
python -m aiService.tests.chatbot_tests
```

This will run all three test objectives:
- **CB-2**: System prompt validation (20 calculus questions)
- **CB-8**: Scope enforcement (10 off-topic questions)
- **CB-9**: Response quality evaluation (answer key matching)

### 3. Expected Output

```
╔══════════════════════════════════════════════════════════╗
║          CalcVoyager Test Suite Execution               ║
║            CB-2, CB-8, CB-9 Combined                    ║
╚══════════════════════════════════════════════════════════╝

============================================================
CB-2: CalcVoyager Acceptance Test
Testing system prompt against 20 calculus questions
============================================================

[1/20] Testing: limits - Q1
  Question: What is the limit of (x² - 4)/(x - 2) as x approaches 2?...
  ✓ PASS - 145 words
  Correctness: 1.00

[... 19 more questions ...]

============================================================
CB-2 RESULTS: 18/20 tests passed
============================================================

Check Breakdown:
  latex_formatting: 20/20
  follow_ups: 19/20
  word_count: 20/20
  step_formatting: 18/20

============================================================
CB-9: Response Quality Evaluation
============================================================

Correctness Scores (answer key matching):
  Q 1: ✓ 1.00
  Q 2: ✓ 0.67
  [... more scores ...]

Overall Correctness: 16/20 questions with score >= 0.6

✓ CB-9 ACCEPTANCE: MET
  Response quality meets accuracy threshold

============================================================
CB-8: Scope Enforcement Test
Testing Cal's refusal of off-topic questions
============================================================

[1/10] Testing: Who was the first president of the United St...
  ✓ REFUSED - Refusal phrase 'I'm Cal' detected

[... 9 more questions ...]

============================================================
SCOPE ENFORCEMENT: 10/10 refused correctly
============================================================

✓ CB-8 ACCEPTANCE: MET
  Cal successfully refuses all off-topic questions

============================================================
COMBINED TEST SUMMARY
============================================================
CB-2 (System Prompt):      ✓ PASS
CB-8 (Scope Enforcement):  ✓ PASS
CB-9 (Quality Evaluation): ✓ PASS
============================================================

🎉 ALL ACCEPTANCE CRITERIA MET
```

## Test Results

Results are automatically saved to:
```
aiService/tests/test_results.json
```

This JSON file contains detailed information including:
- Individual question responses (preview)
- Check results for each question
- Correctness scores
- Word counts
- Pass/fail status
- Overall statistics

## Interpreting Results

### CB-2: System Prompt Validation
- **Pass threshold**: 18/20 questions (90%)
- **What it tests**: LaTeX formatting, follow-ups, word count, step formatting
- **Why it matters**: Ensures Cal follows the system prompt structure

### CB-8: Scope Enforcement
- **Pass threshold**: 10/10 off-topic questions refused (100%)
- **What it tests**: Cal's ability to refuse non-calculus questions
- **Detection criteria**:
  - Response contains "I'm Cal, your calculus tutor"
  - Response does NOT contain step-by-step math solutions

### CB-9: Response Quality Evaluation
- **Pass threshold**: 16/20 questions with correctness >= 0.6 (80%)
- **What it tests**: Mathematical accuracy via answer key matching
- **Scoring method**: Fraction of expected LaTeX fragments found
- **Example**: If answer_key = ["x + 2", "4", "$\\lim$"] and response contains 2/3, score = 0.67

## Troubleshooting

### Mock Mode Still Active
**Symptom**: Tests run instantly with placeholder responses

**Solution**:
```python
# In aiService/services/llm_client.py line 12:
USE_MOCK = False  # Make sure this is False, not True
```

### API Key Error
**Symptom**: "Authentication failed" or similar errors

**Solution**:
1. Check `.env` file location: `aiService/services/.env`
2. Verify GROK_API_KEY is set correctly
3. Ensure no extra spaces or quotes around the key

### Import Errors
**Symptom**: `ModuleNotFoundError: No module named 'openai'`

**Solution**:
```bash
pip install -r aiService/requirements.txt
```

### Path Issues on Windows
**Symptom**: File not found errors

**Solution**: Run from project root directory:
```bash
cd "c:\Users\zaigh\Desktop\Qunatum Logics\Calculus\chatbot\Calculus-AI-Chatbot"
python -m aiService.tests.chatbot_tests
```

## Cost Considerations

- **Total API calls**: 30 (20 calculus + 10 off-topic)
- **Model**: grok-3-mini
- **Max tokens per call**: 1000
- **Estimated cost**: Check xAI pricing for current rates

To minimize costs during development:
- Use `USE_MOCK = True` for code testing
- Only set `USE_MOCK = False` for final validation

## Monitoring Scope Violations

During test execution, watch for WARNING logs:
```
WARNING:root:SCOPE_VIOLATION: possible off-topic response for message: Tell me about...
```

These warnings indicate Cal may have answered an off-topic question instead of refusing it. This helps identify system prompt weaknesses.

## Next Steps After Testing

1. **If tests fail**:
   - Review `test_results.json` for detailed failure reasons
   - Check which questions failed and why
   - Consider refining the system prompt in `llm_client.py`
   - Adjust answer keys if they're too strict

2. **If tests pass**:
   - Review scope violation warnings (if any)
   - Consider adding more edge case questions
   - Document any observed issues for future improvements
   - Proceed with integration testing

## Additional Test Files

- **calculus_questions.json**: Contains 20 test questions with answer keys
- **chatbot_tests.py**: Main test suite implementation
- **test_results.json**: Generated output (git-ignored)

## Support

For questions about:
- Test implementation: See IMPLEMENTATION_SUMMARY.md
- System prompt design: See aiService/readme.md
- API configuration: See aiService/services/.env (create if missing)
