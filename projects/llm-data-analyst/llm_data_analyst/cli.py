import argparse
import sys

from dotenv import load_dotenv

from .agent import DataAnalystAgent
from .db import Database
from .llm_client import LLMClient


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="Ask questions about a CSV in plain English.")
    parser.add_argument("--csv", required=True, help="Path to a CSV file to load as the 'data' table.")
    parser.add_argument("--question", help="Question to ask. Omit to enter interactive mode.")
    args = parser.parse_args()

    db = Database()
    db.load_csv("data", args.csv)
    agent = DataAnalystAgent(db, LLMClient())

    if args.question:
        _ask_and_print(agent, args.question)
        return

    print("Interactive mode. Type a question, or 'exit' to quit.")
    while True:
        question = input("> ").strip()
        if question.lower() in {"exit", "quit"}:
            break
        if not question:
            continue
        _ask_and_print(agent, question)


def _ask_and_print(agent: DataAnalystAgent, question: str):
    try:
        result = agent.ask(question)
    except Exception as exc:  # noqa: BLE001 - top-level CLI boundary
        print(f"Could not answer: {exc}", file=sys.stderr)
        return
    print(f"\nSQL used ({result.attempts} attempt(s)): {result.sql}")
    print(f"\nAnswer: {result.answer}\n")


if __name__ == "__main__":
    main()
