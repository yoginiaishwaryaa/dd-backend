import re

# Hard limit on policy text length
_MAX_LENGTH = 1500

# Prompt injection patterns
_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"ignore\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions?|rules?|prompts?|context)",
        r"disregard\s+(all\s+)?(previous|prior|above|earlier|the\s+above)",
        r"forget\s+(all\s+)?(previous|prior|above|earlier|the\s+above)",
        r"you\s+are\s+now\b",
        r"act\s+as\s+(a\s+|an\s+)?\w+",
        r"pretend\s+(you\s+are|to\s+be)",
        r"your\s+new\s+(role|instructions?|persona)",
        r"override\s+(the\s+)?(system|instructions?|rules?)",
        r"\bsystem\s*:",
        r"\buser\s*:",
        r"\bassistant\s*:",
        r"<\s*/?(?:script|iframe|object|embed|form|input|style)[^>]*>",
        r"```\s*system",
        r"\[\s*system\s*\]",
        r"reveal\s+(your\s+)?(prompt|instructions?|system)",
        r"print\s+(your\s+)?(prompt|instructions?|system)",
        r"what\s+(are|were)\s+your\s+(instructions?|prompt)",
        r"jailbreak",
        r"do\s+anything\s+now",
        r"\bdan\b.*\bmode\b",
    ]
]


# Run the docs_policies through checks and sanitise it before passing to the graph
def validate_and_sanitize_policies(raw_policies: str | None) -> str | None:
    if not raw_policies or not raw_policies.strip():
        return None

    text = raw_policies.strip()

    # Hard length cap
    if len(text) > _MAX_LENGTH:
        print(
            f"validate_policies: docs_policies exceeds {_MAX_LENGTH} chars "
            f"({len(text)}), truncating"
        )
        text = text[:_MAX_LENGTH]

    # Prompt injection check
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            print(
                f"validate_policies: docs_policies rejected — "
                f"matched injection pattern /{pattern.pattern}/"
            )
            return None

    # Strip HTML tags
    text = re.sub(r"<[^>]+>", "", text).strip()

    # After stripping if no text is left, return None
    if not text:
        return None

    return text
