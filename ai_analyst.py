import json
import os
import pandas as pd
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()


MODEL_NAME = "gemini-flash-latest"


def ask_performance_analyst(
    question: str,
    department_summary: pd.DataFrame,
    monthly_summary: pd.DataFrame,
) -> str:
    """Answer dashboard questions using Gemini and actual metrics."""

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        return (
            "Gemini API key not found.\n\n"
            "1. Add GEMINI_API_KEY to your .env file.\n"
            "2. Restart Streamlit.\n"
            "3. Try again."
        )

    if not question or not question.strip():
        return "Please enter a question."

    metrics = {
        "department_metrics": department_summary.to_dict(
            orient="records"
        ),
        "monthly_metrics": monthly_summary.to_dict(
            orient="records"
        ),
    }

    instructions = """
You are WorkforceIQ AI, a workforce performance analyst.

Rules:
1. Use only the supplied dashboard metrics.
2. Quote figures accurately and explain why they matter.
3. Identify departments that may need investigation.
4. Do not invent business events, causes, or statistics.
5. Distinguish observed results from possible explanations.
6. Average KPI achievement is not a complete employee rating.
7. Never recommend hiring, firing, promotion, or disciplinary
   action based solely on performance metrics.
8. If the data cannot answer a question, say so.
9. Give concise, professional Markdown responses.
10. Recommend practical follow-up analyses where appropriate.
"""

    prompt = (
        "DASHBOARD METRICS:\n"
        + json.dumps(metrics, default=str)
        + "\n\nUSER QUESTION:\n"
        + question.strip()
    )

    client = None

    try:
        client = genai.Client(api_key=api_key)

        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=instructions,
                temperature=0.2,
                max_output_tokens=1200,
            ),
        )

        answer = response.text

        if not answer:
            return (
                "Gemini returned no text. Try rephrasing your question."
            )

        return answer

    except Exception as error:
        error_name = type(error).__name__

        return (
            "Gemini API request failed.\n\n"
            f"Error type: {error_name}\n\n"
            "Check your API key, internet connection, model access, "
            "API quota, and billing settings. Do not share your API key."
        )

    finally:
        if client is not None:
            client.close()
