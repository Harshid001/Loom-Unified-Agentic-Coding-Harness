from typing import Dict


class ContextSummarizer:
    """Hierarchical summarization for large files and directory listings."""

    def summarize_files(self, files_dict: Dict[str, str], max_summary_lines: int = 10) -> str:
        summary_lines = ["### Repository File Summaries:"]
        for path, content in files_dict.items():
            lines = content.splitlines()
            line_count = len(lines)
            preview = "\n".join(lines[:max_summary_lines])
            summary_lines.append(f"File: {path} ({line_count} lines)\nPreview:\n{preview}\n---")
        return "\n".join(summary_lines)
