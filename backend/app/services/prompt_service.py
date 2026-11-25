"""Loads versioned prompt templates from app/prompts/ ($placeholders, string.Template)."""

from functools import cache
from pathlib import Path
from string import Template

PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts"
# Active version per template. Older files are kept for comparison; bump a
# version by adding <name>_vN.md and changing it here.
PROMPT_VERSIONS = {"system": "v4", "chunk": "v2", "merge": "v2", "single": "v2"}


@cache
def _template(name: str) -> Template:
    return Template((PROMPT_DIR / f"{name}_{PROMPT_VERSIONS[name]}.md").read_text(encoding="utf-8"))


def render(name: str, **values: object) -> str:
    """Fills a template. Missing placeholders raise KeyError (no silent blanks)."""
    return _template(name).substitute({k: str(v) for k, v in values.items()})


def system_prompt(glossary: str = "") -> str:
    """System rules, plus the project glossary section when there is one."""
    base = render("system")
    return f"{base.rstrip()}\n\n{glossary}\n" if glossary else base
