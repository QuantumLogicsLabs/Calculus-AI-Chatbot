import uuid
import re
from services.math_verifier import verify_cal_math

def generate_problem(topic: str):
    """Return (problem_text, hidden_answer) with proper SymPy syntax."""
    if topic == "derivatives":
        problem_text = "Find the derivative of x**3."
        solution_text = "3*x**2"
    elif topic == "integrals":
        problem_text = "Find the integral of 2*x."
        solution_text = "x**2"
    else:
        problem_text = "Simplify: x + x + x."
        solution_text = "3*x"
    return problem_text, solution_text

def preprocess_math_expr(expr: str) -> str:
    """Convert common math notations to SymPy-compatible syntax."""
    # Replace ^ with **
    expr = expr.replace('^', '**')
    # Insert * between number and letter (e.g., 2x -> 2*x)
    expr = re.sub(r'(\d)([a-zA-Z])', r'\1*\2', expr)
    # Insert * between letter and number (e.g., x2 -> x*2) – rare but safe
    expr = re.sub(r'([a-zA-Z])(\d)', r'\1*\2', expr)
    return expr

def check_answer(problem: str, user_answer: str):
    """
    Use CB-16 verifier to check if user's answer is correct.
    Preprocess the problem text as well (since it's used by the verifier).
    """
    # Preprocess the problem text to make it parseable (the verifier extracts the expression)
    # Actually we need to ensure that the verifier's parse_operation extracts the expression
    # with proper syntax. Since we control the problem text, we can just write it correctly.
    # However, the verifier also uses sympify on the user's answer, so we preprocess that too.
    # But the verifier uses the problem string as is – we can either modify the problem
    # generation to use proper syntax (already done), or we can temporarily change the
    # verifier to preprocess. For simplicity, we'll ensure the problem is correct.
    
    # But the user answer might contain ^ or implicit multiplication, so we preprocess it
    # before passing to the verifier (we wrap it in \boxed{...})
    user_answer_processed = preprocess_math_expr(user_answer)
    
    is_correct, sympy_result, error = verify_cal_math(
        question_text=problem,
        cal_response=f"\\boxed{{{user_answer_processed}}}"
    )
    return is_correct, sympy_result, error

def main():
    print("🧮 Welcome to the Math Practice CLI!")
    print("Available topics: derivatives, integrals, simplify")
    while True:
        topic = input("\nEnter topic (or 'exit' to quit): ").strip().lower()
        if topic == 'exit':
            break
        if topic not in ["derivatives", "integrals", "simplify"]:
            print("Unknown topic. Try: derivatives, integrals, simplify")
            continue

        # Generate problem
        problem, hidden = generate_problem(topic)
        print(f"\n📝 Problem: {problem}")
        
        # Get user's answer
        user_ans = input("Your answer: ").strip()
        if not user_ans:
            print("You didn't enter anything. Try again.")
            continue
        
        # Verify
        correct, sym_answer, error = check_answer(problem, user_ans)
        
        if error:
            print(f"⚠️ Error: {error}")
        elif correct:
            print("✅ Perfect! That's correct!")
        else:
            correct_display = sym_answer if sym_answer else hidden
            print(f"❌ Not quite. The correct answer is: {correct_display}")

if __name__ == "__main__":
    main()