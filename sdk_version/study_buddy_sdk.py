"""Study Buddy - SDK version.

A small agent that calls OpenAI through the official Python SDK (the `openai` library):
  1. The model analyzes the study material and decides which action fits.
  2. The code performs that action - only "generate_questions" makes a second call.
"""

import json
import os

import openai
from dotenv import load_dotenv
from openai import OpenAI

REQUEST_TIMEOUT_SECONDS = 120
MAX_OUTPUT_TOKENS = 16000

# The three actions the agent can choose from.
GENERATE_QUESTIONS = "generate_questions"
REQUEST_MORE_MATERIAL = "request_more_material"
CANNOT_PROCEED = "cannot_proceed"
ACTIONS = (GENERATE_QUESTIONS, REQUEST_MORE_MATERIAL, CANNOT_PROCEED)

NUM_QUESTIONS = 5
REQUIRED_FIELDS = ("question", "answer", "explanation", "difficulty")
DIFFICULTY_LEVELS = ("easy", "medium", "hard")

# ---------- Step 1: decision ----------

DECISION_INSTRUCTIONS = f"""You are Study Buddy, a study assistant for students.
Analyze the text you receive and decide which action fits it. Do not write questions now.

Actions:
- {GENERATE_QUESTIONS}: the text is study material with enough content
  for {NUM_QUESTIONS} different practice questions.
- {REQUEST_MORE_MATERIAL}: the text is about a topic that can be studied,
  but it is too short or missing information for {NUM_QUESTIONS} questions.
- {CANNOT_PROCEED}: the text is not study material, or it has no content
  that practice questions can be based on.

In "reason", speak to the user in the same language as the text:
- for {REQUEST_MORE_MATERIAL}: say what material to add.
- for {CANNOT_PROCEED}: explain why questions cannot be created.
- for {GENERATE_QUESTIONS}: briefly say why the material is suitable."""

DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": list(ACTIONS)},
        "reason": {"type": "string"},
    },
    "required": ["action", "reason"],
    "additionalProperties": False,
}

# ---------- Step 2: question generation ----------

QUESTIONS_INSTRUCTIONS = f"""You are Study Buddy, a study assistant for students.
You receive study material (a lesson summary or notes).
Write exactly {NUM_QUESTIONS} practice questions about this material.

Rules:
- Every question must test a concept that appears in the material.
- You may use general knowledge to phrase and check the answer and the explanation.
- Each question needs: the question, the correct answer, a short explanation,
  and a difficulty level: easy, medium or hard.
- Write in the same language as the material."""

QUESTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "answer": {"type": "string"},
                    "explanation": {"type": "string"},
                    "difficulty": {"type": "string", "enum": list(DIFFICULTY_LEVELS)},
                },
                "required": list(REQUIRED_FIELDS),
                "additionalProperties": False,
            },
        }
    },
    "required": ["questions"],
    "additionalProperties": False,
}


class StudyBuddyError(Exception):
    """An expected failure with a message that can be shown to the user."""


# ---------- Communication with the API through the SDK ----------

def load_config() -> tuple[str, str]:
    """Read the API key and model name from the .env file."""
    load_dotenv(override=True)  # values in .env take priority over system variables
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL")
    if not api_key or not model:
        raise StudyBuddyError("OPENAI_API_KEY and OPENAI_MODEL must be set in the .env file.")
    return api_key, model


def call_model(client: OpenAI, model: str, instructions: str, schema_name: str, schema: dict, study_text: str) -> dict:
    """One full model call: send the request, check the response, parse it as JSON."""
    try:
        response = client.responses.create(
            model=model,
            instructions=instructions,
            input=study_text,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            text={
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "schema": schema,
                    "strict": True,
                }
            },
        )
    except openai.APITimeoutError:
        raise StudyBuddyError("The request timed out. Try again.")
    except openai.APIConnectionError as error:
        raise StudyBuddyError(f"Could not connect to the OpenAI API: {error.__cause__ or error}")
    except openai.APIStatusError as error:
        raise StudyBuddyError(f"HTTP {error.status_code}: {error.message}")

    if response.status != "completed":
        details = response.incomplete_details or response.error
        raise StudyBuddyError(f"The model did not finish (status: {response.status}, details: {details}).")

    for item in response.output:
        if item.type == "message":
            for part in item.content:
                if part.type == "refusal":
                    raise StudyBuddyError(f"The model refused: {part.refusal}")

    if not response.output_text:
        raise StudyBuddyError("No text was found in the model's response.")
    try:
        return json.loads(response.output_text)
    except json.JSONDecodeError:
        raise StudyBuddyError("The model's output is not valid JSON.")


# ---------- Agent steps ----------

def decide_action(client: OpenAI, model: str, study_text: str) -> dict:
    """Step 1: the model analyzes the material and chooses an action."""
    decision = call_model(client, model, DECISION_INSTRUCTIONS, "decision", DECISION_SCHEMA, study_text)
    if decision.get("action") not in ACTIONS or not isinstance(decision.get("reason"), str):
        raise StudyBuddyError(f"The model returned an invalid decision: {decision}")
    return decision


def generate_questions(client: OpenAI, model: str, study_text: str) -> list[dict]:
    """Step 2: the model writes the practice questions."""
    result = call_model(client, model, QUESTIONS_INSTRUCTIONS, "study_questions", QUESTIONS_SCHEMA, study_text)
    validate_questions(result)
    return result["questions"]


def validate_questions(result: dict) -> None:
    """Make sure the result holds exactly NUM_QUESTIONS complete questions."""
    questions = result.get("questions")
    if not isinstance(questions, list) or len(questions) != NUM_QUESTIONS:
        count = len(questions) if isinstance(questions, list) else 0
        raise StudyBuddyError(f"Expected {NUM_QUESTIONS} questions, got {count}.")

    for number, question in enumerate(questions, start=1):
        if not isinstance(question, dict):
            raise StudyBuddyError(f"Question {number} is not a JSON object.")
        missing = [
            field for field in REQUIRED_FIELDS
            if not isinstance(question.get(field), str) or not question[field].strip()
        ]
        if missing:
            raise StudyBuddyError(f"Question {number} is missing fields: {', '.join(missing)}.")
        if question["difficulty"] not in DIFFICULTY_LEVELS:
            raise StudyBuddyError(f"Question {number} has an invalid difficulty: {question['difficulty']}.")


def run_agent(study_text: str) -> dict:
    """Analyze -> decide -> act. Returns the final JSON result."""
    api_key, model = load_config()
    client = OpenAI(api_key=api_key, timeout=REQUEST_TIMEOUT_SECONDS)  # retries twice by default
    decision = decide_action(client, model, study_text)
    action = decision["action"]

    if action == GENERATE_QUESTIONS:
        return {"action": action, "questions": generate_questions(client, model, study_text)}

    # REQUEST_MORE_MATERIAL or CANNOT_PROCEED: no questions are generated,
    # the model's message tells the user what to add or why we stop.
    return {"action": action, "message": decision["reason"]}
