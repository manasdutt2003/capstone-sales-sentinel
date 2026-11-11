import os
import sys

import anthropic
from dotenv import load_dotenv

# read ANTHROPIC_API_KEY from .env so it never sits in the code
load_dotenv()
api_key = os.getenv("ANTHROPIC_API_KEY")

# stop here if there's no key, before anything talks to the API
if not api_key:
    print("Error: ANTHROPIC_API_KEY is not set.")
    sys.exit(1)

client = anthropic.Anthropic(api_key=api_key)


def extract_invoice(text: str) -> str:
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=800,
        messages=[{"role": "user", "content": text}]
    )
    return response.content[0].text
