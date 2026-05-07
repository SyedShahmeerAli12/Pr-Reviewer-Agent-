import re

import httpx

_GITHUB_API = "https://api.github.com"
_files_cache: dict[str, list[dict]] = {}


def _parse_pr_url(pr_url: str) -> tuple[str, str, int]:
    match = re.match(r"https://github\.com/([^/]+)/([^/]+)/pull/(\d+)", pr_url.strip())
    if not match:
        msg = f"Invalid GitHub PR URL: {pr_url}"
        raise ValueError(msg)
    return match.group(1), match.group(2), int(match.group(3))


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"}


def _get_pr_files(owner: str, repo: str, number: int, token: str) -> list[dict]:
    cache_key = f"{owner}/{repo}/{number}"
    if cache_key not in _files_cache:
        resp = httpx.get(
            f"{_GITHUB_API}/repos/{owner}/{repo}/pulls/{number}/files",
            headers=_headers(token),
            params={"per_page": 50},
            timeout=15,
        )
        resp.raise_for_status()
        _files_cache[cache_key] = resp.json()
    return _files_cache[cache_key]


def get_pr_overview(pr_url: str, token: str) -> dict:
    owner, repo, number = _parse_pr_url(pr_url)

    pr = httpx.get(f"{_GITHUB_API}/repos/{owner}/{repo}/pulls/{number}", headers=_headers(token), timeout=15)
    pr.raise_for_status()
    pr_data = pr.json()

    files = _get_pr_files(owner, repo, number, token)

    return {
        "title": pr_data["title"],
        "description": pr_data.get("body") or "",
        "author": pr_data["user"]["login"],
        "base_branch": pr_data["base"]["ref"],
        "files": [
            {
                "filename": f["filename"],
                "status": f["status"],
                "additions": f["additions"],
                "deletions": f["deletions"],
            }
            for f in files
        ],
    }


def _build_line_to_position(patch: str) -> dict[int, int]:
    """Map new-file line numbers to their 1-based diff position (what GitHub needs for inline comments)."""
    mapping: dict[int, int] = {}
    position = 0
    new_line = 0
    for line in patch.splitlines():
        position += 1
        if line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            if m:
                new_line = int(m.group(1)) - 1
        elif line.startswith("-"):
            pass
        else:
            new_line += 1
            mapping[new_line] = position
    return mapping


def get_file_patch(pr_url: str, filename: str, token: str) -> str:
    owner, repo, number = _parse_pr_url(pr_url)
    files = _get_pr_files(owner, repo, number, token)

    for f in files:
        if f["filename"] == filename:
            patch = f.get("patch")
            if not patch:
                return "No diff available (binary file or no changes)."
            mapping = _build_line_to_position(patch)
            added_lines = [ln for ln, pos in mapping.items()]
            header = f"[VALID LINE NUMBERS FOR INLINE COMMENTS: {sorted(added_lines)}]\n"
            return header + patch

    return f"File '{filename}' not found in this PR."


def post_pr_review(pr_url: str, body: str, inline_comments: list[dict], token: str) -> str:
    owner, repo, number = _parse_pr_url(pr_url)

    files = _get_pr_files(owner, repo, number, token)
    position_maps: dict[str, dict[int, int]] = {
        f["filename"]: _build_line_to_position(f["patch"])
        for f in files
        if f.get("patch")
    }

    formatted_comments = []
    for c in inline_comments:
        if not (c.get("path") and c.get("line") and c.get("body")):
            continue
        pos_map = position_maps.get(c["path"], {})
        position = pos_map.get(int(c["line"]))
        if position is None:
            continue
        formatted_comments.append({"path": c["path"], "position": position, "body": c["body"]})

    payload: dict = {"body": body, "event": "COMMENT"}
    if formatted_comments:
        payload["comments"] = formatted_comments

    resp = httpx.post(
        f"{_GITHUB_API}/repos/{owner}/{repo}/pulls/{number}/reviews",
        headers=_headers(token),
        json=payload,
        timeout=20,
    )

    if resp.status_code == 422 and formatted_comments:
        payload.pop("comments")
        resp = httpx.post(
            f"{_GITHUB_API}/repos/{owner}/{repo}/pulls/{number}/reviews",
            headers=_headers(token),
            json=payload,
            timeout=20,
        )

    resp.raise_for_status()
    return f"Review posted: {resp.json().get('html_url', 'success')}"
