# PR Reviewer

An AI agent that automatically reviews GitHub pull requests and posts inline comments — built with [Haystack](https://haystack.deepset.ai/) by deepset.

## How it works

Haystack is an open-source AI framework for building pipelines and agents. This project uses its `Agent` and `Tool` system to create a code reviewer that can fetch PR data, read diffs, check conventions, and post feedback — all on its own.

The agent gets one instruction: *review this PR*. It then decides which tools to call and in what order, without any hardcoded steps.

**Tools the agent has:**

| Tool | What it does |
|------|-------------|
| `fetch_pr_overview` | Gets PR title, description, author, and list of changed files |
| `fetch_file_diff` | Gets the actual code diff for a specific file |
| `query_conventions` | Checks a local SQLite database of coding rules |
| `post_github_review` | Posts the final review with inline comments to GitHub |

## Setup

```bash
git clone https://github.com/SyedShahmeerAli12/Pr-Reviewer-Agent-.git
cd Pr-Reviewer-Agent-
pip install -r requirements.txt
cp .env.example .env            # fill in your keys
```

## Usage

```bash
pr-reviewer https://github.com/owner/repo/pull/123

# Preview without posting
pr-reviewer https://github.com/owner/repo/pull/123 --dry-run
```

## Supported LLM providers

Set `LLM_PROVIDER` in `.env` to one of:

- `openai` — requires `OPENAI_API_KEY`
- `anthropic` — requires `ANTHROPIC_API_KEY`
- `ollama` — free, runs locally (pull `qwen2.5-coder:7b` first)

## Requirements

- Python 3.10+
- GitHub token with `repo` scope
