import os
from typing import Any, Callable

from haystack.components.agents import Agent
from haystack.dataclasses import ChatMessage, StreamingChunk
from haystack.tools import Tool

from pr_reviewer.db import query_db, save_review, setup_db
from pr_reviewer.github import get_file_patch, get_pr_overview, post_pr_review

SYSTEM_PROMPT = """You are an expert code reviewer. You MUST always complete your work by calling the post_github_review tool — never output the review as text.

You have four tools:
- fetch_pr_overview     — get the PR title, description, author, and list of changed files
- fetch_file_diff       — get the actual code diff (patch) for a specific file
- query_conventions     — run a SQL query against the coding conventions database
- post_github_review    — REQUIRED: post your completed review to GitHub

Your review process — follow these steps in order:
1. Call fetch_pr_overview.
2. Call fetch_file_diff for each changed file.
3. Call query_conventions to check relevant rules (e.g. SELECT * FROM conventions).
4. Call post_github_review with your summary and inline_comments. THIS IS MANDATORY — you must call this tool, do not just write the review as text.

Rules for good reviews:
- Reference actual code lines in your comments ("On line 42, `fetch_data` has no return type hint")
- Be constructive — explain WHY something is an issue, not just WHAT
- Do NOT flag linting issues (formatting, line length)
- If code is clean, say so — a positive review is valid
- Focus on: hardcoded secrets, bare excepts, missing docstrings, debug logs left in, missing type hints
- Each diff returned by fetch_file_diff starts with [VALID LINES FOR INLINE COMMENTS: [...]]. You MUST only use line numbers from that list for inline comments — using any other line number will cause the review to fail.

IMPORTANT: You are not done until you have called post_github_review. Do not output the review as plain text."""


def _make_streaming_callback(console: Any) -> Callable:
    """Return a streaming callback that prints token-by-token output to the console."""
    def on_chunk(chunk: StreamingChunk) -> None:
        if chunk.content:
            console.print(chunk.content, end="", highlight=False)
    return on_chunk


def build_agent(db_path: str = "pr_reviewer.db", streaming_callback: Callable | None = None) -> Agent:
    token = os.environ.get("GITHUB_TOKEN", "")
    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    setup_db(db_path)

    def fetch_pr_overview(pr_url: str) -> str:
        info = get_pr_overview(pr_url, token)
        files_list = "\n".join(
            f"  - {f['filename']} [{f['status']}] +{f['additions']}/-{f['deletions']}"
            for f in info["files"]
        )
        return (
            f"Title: {info['title']}\n"
            f"Author: {info['author']}\n"
            f"Base branch: {info['base_branch']}\n"
            f"Description: {info['description'] or '(none)'}\n\n"
            f"Changed files:\n{files_list}"
        )

    def fetch_file_diff(pr_url: str, filename: str) -> str:
        return get_file_patch(pr_url, filename, token)

    def query_conventions(sql: str) -> str:
        return query_db(db_path, sql)

    def post_github_review(pr_url: str, summary: str, inline_comments: list[dict]) -> str:
        result = post_pr_review(pr_url, summary, inline_comments, token)
        for c in inline_comments:
            if c.get("path") and c.get("body"):
                save_review(db_path, pr_url, c["path"], "inline", c["body"])
        return result

    tools = [
        Tool(
            name="fetch_pr_overview",
            description="Fetch the title, description, author, and list of changed files for a GitHub PR.",
            parameters={
                "type": "object",
                "properties": {
                    "pr_url": {"type": "string", "description": "Full GitHub PR URL, e.g. https://github.com/owner/repo/pull/123"},
                },
                "required": ["pr_url"],
            },
            function=fetch_pr_overview,
        ),
        Tool(
            name="fetch_file_diff",
            description="Fetch the diff (patch) for a specific file in a GitHub PR.",
            parameters={
                "type": "object",
                "properties": {
                    "pr_url": {"type": "string", "description": "Full GitHub PR URL"},
                    "filename": {"type": "string", "description": "File path as shown in the PR, e.g. src/module/utils.py"},
                },
                "required": ["pr_url", "filename"],
            },
            function=fetch_file_diff,
        ),
        Tool(
            name="query_conventions",
            description=(
                "Query the coding conventions database using SQL. "
                "Table: conventions(id, category, rule, example, file_pattern). "
                "Categories: imports, docstrings, naming, testing, errors, types, general, security. "
                "Example: SELECT * FROM conventions WHERE category = 'testing'"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "A SQL SELECT query against the conventions table"},
                },
                "required": ["sql"],
            },
            function=query_conventions,
        ),
        Tool(
            name="post_github_review",
            description="Post the completed code review to GitHub. Call this once when you are done reviewing all files.",
            parameters={
                "type": "object",
                "properties": {
                    "pr_url": {"type": "string", "description": "Full GitHub PR URL"},
                    "summary": {"type": "string", "description": "Overall review summary — what the PR does, what is good, what needs fixing"},
                    "inline_comments": {
                        "type": "array",
                        "description": "Inline comments on specific lines. Use line numbers from the new (right) side of the diff.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "path": {"type": "string", "description": "File path"},
                                "line": {"type": "integer", "description": "Line number in the new file"},
                                "body": {"type": "string", "description": "Comment text — specific and actionable"},
                            },
                            "required": ["path", "line", "body"],
                        },
                    },
                },
                "required": ["pr_url", "summary", "inline_comments"],
            },
            function=post_github_review,
        ),
    ]

    if provider == "openai":
        from haystack.components.generators.chat import OpenAIChatGenerator
        model = os.environ.get("OPENAI_MODEL", "gpt-4o")
        chat_generator = OpenAIChatGenerator(
            model=model,
            streaming_callback=streaming_callback,
        )
    elif provider == "anthropic":
        from haystack_integrations.components.generators.anthropic import AnthropicChatGenerator
        model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        chat_generator = AnthropicChatGenerator(
            model=model,
            streaming_callback=streaming_callback,
        )
    else:
        from haystack_integrations.components.generators.ollama import OllamaChatGenerator
        model = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")
        chat_generator = OllamaChatGenerator(
            model=model,
            streaming_callback=streaming_callback,
        )

    return Agent(
        chat_generator=chat_generator,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        max_agent_steps=30,
        raise_on_tool_invocation_failure=False,
    )


def run_review(pr_url: str, db_path: str = "pr_reviewer.db", dry_run: bool = False, console: Any = None) -> str:  # noqa: FBT001, FBT002
    system_prompt = SYSTEM_PROMPT
    if dry_run:
        system_prompt += "\n\nDRY RUN MODE: Do NOT call post_github_review. Instead, end your response with the full review text you would have posted."

    streaming_callback = _make_streaming_callback(console) if console else None
    agent = build_agent(db_path, streaming_callback=streaming_callback)

    # Patch system prompt for dry run after build
    if dry_run:
        agent.system_prompt = system_prompt

    result = agent.run(messages=[ChatMessage.from_user(f"Please review this pull request: {pr_url}")])
    messages = result.get("messages", [])
    for msg in reversed(messages):
        if hasattr(msg, "role") and "assistant" in str(msg.role).lower() and not getattr(msg, "tool_calls", None):
            return msg.text or str(msg)
    return "Review completed. Check GitHub for posted comments."
