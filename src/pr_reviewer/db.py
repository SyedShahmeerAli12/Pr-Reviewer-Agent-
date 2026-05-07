import sqlite3
from contextlib import contextmanager

_CONVENTIONS = [
    (1,  'imports',  'Use absolute imports — no relative imports from parent packages', 'from haystack.utils import Secret  -- correct', '*.py'),
    (2,  'imports',  'Group imports: stdlib, then third-party, then local — blank line between each group', '', '*.py'),
    (3,  'docstrings', 'All public methods need docstrings with param and returns sections', '', '*.py'),
    (4,  'docstrings', 'Component run() and __init__() must always have docstrings', '', '*.py'),
    (5,  'naming',   'Functions and variables use snake_case; classes use PascalCase', '', '*.py'),
    (6,  'testing',  'Unit tests must not make real network calls — mock all external services', '', 'test_*.py'),
    (7,  'testing',  'Each test function tests exactly one behaviour; name reflects what it tests', 'def test_run_returns_empty_list_when_no_documents', 'test_*.py'),
    (8,  'errors',   'Catch specific exception types — never bare except clauses', 'except ValueError as e: -- correct', '*.py'),
    (9,  'types',    'All public function signatures must have complete type hints', 'def run(self, query: str) -> dict[str, Any]:', '*.py'),
    (10, 'general',  'No print() or console.log() in production code — use a logger', 'logger = logging.getLogger(__name__)', '*.py'),
    (11, 'general',  'Keep functions under 50 lines; extract helpers if longer', '', '*.py'),
    (12, 'general',  'Haystack components must implement to_dict() and from_dict() for serialization', '', '*.py'),
    (13, 'security', 'Never hardcode secrets or tokens in source code — use environment variables', 'Secret.from_env_var("API_KEY")', '*.py'),
    (14, 'testing',  'Test files must import only from the public API of the module under test', '', 'test_*.py'),
]


@contextmanager
def _connect(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def setup_db(db_path: str = "pr_reviewer.db") -> str:
    with _connect(db_path) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS conventions (
            id INTEGER PRIMARY KEY,
            category TEXT NOT NULL,
            rule TEXT NOT NULL,
            example TEXT DEFAULT '',
            file_pattern TEXT DEFAULT '*'
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS review_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pr_url TEXT NOT NULL,
            filename TEXT NOT NULL,
            issue_type TEXT NOT NULL,
            comment TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        conn.executemany(
            "INSERT OR IGNORE INTO conventions (id, category, rule, example, file_pattern) VALUES (?,?,?,?,?)",
            _CONVENTIONS,
        )
    return db_path


def query_db(db_path: str, sql: str) -> str:
    try:
        with _connect(db_path) as conn:
            cursor = conn.execute(sql)
            rows = cursor.fetchall()
            if not rows:
                return "No results found."
            cols = [d[0] for d in cursor.description]
            lines = [" | ".join(cols)]
            lines.append("-" * len(lines[0]))
            for row in rows:
                lines.append(" | ".join(str(v) for v in row))
            return "\n".join(lines)
    except Exception as e:
        return f"Query error: {e}"


def save_review(db_path: str, pr_url: str, filename: str, issue_type: str, comment: str) -> None:
    try:
        with _connect(db_path) as conn:
            conn.execute(
                "INSERT INTO review_history (pr_url, filename, issue_type, comment) VALUES (?,?,?,?)",
                (pr_url, filename, issue_type, comment[:200]),
            )
    except Exception:
        pass
