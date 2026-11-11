"""text-tools: a small stdio MCP server with two text utilities.

Run by hand:   uv run --with "mcp[cli]<2" python tools/mcp/server.py
Registered for everyone who clones the repo in .mcp.json (project scope).

Never print() to stdout in a stdio server: stdout carries the MCP protocol,
so stray output corrupts it. Use stderr for any debugging.
"""

import re
import unicodedata

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("text-tools")

# A word is a run of letters/digits, optionally joined by an apostrophe or
# hyphen ("don't", "well-known"). Punctuation is not part of a word, so
# "World!" counts as "World" when finding the longest word.
WORD_RE = re.compile(r"[^\W_]+(?:['\-][^\W_]+)*")


@mcp.tool()
def word_stats(text: str) -> dict:
    """Return the word count, character count and longest word of the text.

    characters counts every character including spaces and punctuation;
    characters_no_spaces excludes whitespace. If several words tie for
    longest, the first one wins. Empty text gives zeros and "".
    """
    words = WORD_RE.findall(text)
    return {
        "word_count": len(words),
        "character_count": len(text),
        "characters_no_spaces": sum(1 for c in text if not c.isspace()),
        "longest_word": max(words, key=len) if words else "",
    }


@mcp.tool()
def slugify(text: str) -> str:
    """Turn text into a lowercase, hyphen-separated URL slug.

    Example: "Hello, World!" -> "hello-world". Accents are folded to ASCII
    ("Café" -> "cafe"); every other run of non-alphanumerics becomes one
    hyphen, with no leading or trailing hyphen.
    """
    ascii_text = (
        unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    )
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


if __name__ == "__main__":
    mcp.run()  # stdio transport by default
