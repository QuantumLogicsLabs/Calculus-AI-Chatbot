import sys
import os

# Add the project root to Python path so we can import 'services'
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.math_verifier import verify_cal_math, extract_boxed_answer

def run_verification(question: str, cal_response: str):
    """
    A helper function to run the verification and print pretty results.
    """
    print("\n" + "="*50)
    print(f"📝 Question: {question}")
    print("-"*50)
    
    # Run the verification
    is_correct, sympy_answer, error = verify_cal_math(question, cal_response)
    
    # Extract Cal's boxed answer for display
    cal_boxed = extract_boxed_answer(cal_response)
    
    print(f"🤖 Cal's Answer: {cal_boxed}")
    print(f"✅ SymPy's Answer: {sympy_answer}")
    
    if error:
        print(f"⚠️  Error: {error}")
    else:
        if is_correct:
            print("🎉 VERDICT: CORRECT! Cal got it right.")
        else:
            print("❌ VERDICT: WRONG! Cal made a mistake.")
    print("="*50)

def main():
    """
    Main entry point - demonstrates the verifier with sample cases.
    You can replace these samples with real data from your API or database.
    """
    
    # --- SAMPLE TEST CASES (Replace with actual data later) ---
    
    cases = [
        {
            "question": "Find the derivative of x**3",
            "cal_response": "The derivative is \\boxed{3*x**2}"
        },
        {
            "question": "Integrate 2*x with respect to x",
            "cal_response": "The integral is \\boxed{x**2 + C}"  # Note: SymPy ignores constant
        },
        {
            "question": "Simplify (x**2 + 2*x + 1)",
            "cal_response": "The simplified form is \\boxed{(x+1)**2}"
        },
        {
            "question": "Find the derivative of sin(x)",
            "cal_response": "The answer is \\boxed{cos(x)}"
        }
    ]
    
    # Run each test case
    for case in cases:
        run_verification(case["question"], case["cal_response"])
    
    # --- OPTIONAL: Interactive mode (uncomment to use) ---
    # while True:
    #     print("\n🔍 Enter a question (or type 'exit' to quit):")
    #     q = input("Question: ")
    #     if q.lower() == 'exit':
    #         break
    #     print("Enter Cal's response (with \\boxed{...}):")
    #     resp = input("Cal: ")
    #     run_verification(q, resp)

if __name__ == "__main__":
    main()