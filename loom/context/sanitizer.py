import re


class PromptSanitizer:
    """Sanitizes untrusted repository file content to prevent prompt injection."""

    INJECTION_PATTERNS = [
        re.compile(r"ignore\s+(previous|all)\s+instructions", re.IGNORECASE),
        re.compile(r"system\s*:\s*", re.IGNORECASE),
        re.compile(r"you\s+are\s+now\s+a", re.IGNORECASE),
        re.compile(r"<\|im_start\|>", re.IGNORECASE),
    ]

    def wrap_untrusted_content(self, content: str, file_path: str) -> str:
        """Wraps untrusted code file content in clear delimiter tags and strips injection strings."""
        clean_text = content
        for pattern in self.INJECTION_PATTERNS:
            clean_text = pattern.sub("[SANITIZED_INSTRUCTION]", clean_text)

        return f'<untrusted_file_content path="{file_path}">\n{clean_text}\n</untrusted_file_content>'
