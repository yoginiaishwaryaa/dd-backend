import textwrap
from unittest.mock import MagicMock, patch

from app.agents.nodes.scout_changes import (
    scout_changes,
    _extract_elements_from_source,
)
from app.agents.state import DriftAnalysisState


# =========== Helper Functions ===========


# Helper function to build a mock CodeChange row
def _make_code_change(
    file_path: str, change_type: str = "modified", is_code: bool = True, is_ignored: bool = False
):
    cc = MagicMock()
    cc.file_path = file_path
    cc.change_type = change_type
    cc.is_code = is_code
    cc.is_ignored = is_ignored
    return cc


# Helper function to build a minimal state dict
def _make_state(
    drift_event_id: str = "evt-1",
    repo_path: str = "/tmp/repo",
    base_sha: str = "abc123def4",
    code_changes: list | None = None,
) -> DriftAnalysisState:
    session = MagicMock()
    filtered = [cc for cc in (code_changes or []) if not cc.is_ignored]
    session.query.return_value.filter.return_value.all.return_value = filtered

    return {
        "drift_event_id": drift_event_id,
        "base_sha": base_sha,
        "head_sha": "def456abc7",
        "session": session,
        "repo_path": repo_path,
        "docs_root_path": "/docs",
        "change_elements": [],
        "analysis_payloads": [],
        "findings": [],
        "target_files": [],
        "rewrite_results": [],
        "style_preference": "professional",
    }


# =========== Tests ===========


# Tests that classes and functions are extracted from source code.
def test_extract_elements_from_source_classes_and_functions():
    source = textwrap.dedent("""\
        class Foo:
            pass

        def bar():
            pass
    """)
    assert _extract_elements_from_source(source) == ["Foo", "bar"]


# Tests that names and route paths are extracted from decorated functions.
def test_extract_elements_from_source_with_routes():
    source = textwrap.dedent("""\
        from flask import Flask
        app = Flask(__name__)

        @app.route('/today')
        def get_date():
            return "today"
    """)
    elements = _extract_elements_from_source(source)
    assert "get_date" in elements
    assert "/today" in elements


# Tests that syntax errors in the source code don't raise exceptions.
def test_extract_elements_from_source_syntax_error():
    assert _extract_elements_from_source("def broken(:\n") == []


# Tests that classes and functions are extracted from a valid Python file.
def test_scout_changes_extracts_elements(tmp_path):
    source = textwrap.dedent("""\
        class UserController:
            pass

        def create_user():
            pass

        def delete_user():
            pass
    """)
    py_file = tmp_path / "src" / "controllers.py"
    py_file.parent.mkdir(parents=True)
    py_file.write_text(source)

    cc = _make_code_change("src/controllers.py", "added")
    state = _make_state(repo_path=str(tmp_path), code_changes=[cc])

    result = scout_changes(state)

    assert len(result["change_elements"]) == 1
    elem = result["change_elements"][0]
    assert elem["file_path"] == "src/controllers.py"
    assert elem["elements"] == ["UserController", "create_user", "delete_user"]
    assert elem["old_elements"] == []


# Tests that async def functions are extracted alongside sync ones.
def test_scout_changes_async_functions(tmp_path):
    source = textwrap.dedent("""\
        async def fetch_data():
            pass

        def process_data():
            pass

        class DataPipeline:
            pass
    """)
    py_file = tmp_path / "pipeline.py"
    py_file.write_text(source)

    cc = _make_code_change("pipeline.py", "added")
    state = _make_state(repo_path=str(tmp_path), code_changes=[cc])

    result = scout_changes(state)

    assert result["change_elements"][0]["elements"] == [
        "fetch_data",
        "process_data",
        "DataPipeline",
    ]
    assert result["change_elements"][0]["old_elements"] == []


# Tests that a modified file gets elements from head and old_elements from base.
def test_scout_changes_modified_extracts_old_and_new(tmp_path):
    # New version on disk
    new_source = textwrap.dedent("""\
        from flask import Flask
        app = Flask(__name__)

        @app.route('/today')
        def get_date():
            return "today"
    """)
    py_file = tmp_path / "routes.py"
    py_file.write_text(new_source)

    # Old version from git
    old_source = textwrap.dedent("""\
        from flask import Flask
        app = Flask(__name__)

        @app.route('/date')
        def get_date():
            return "date"
    """)

    cc = _make_code_change("routes.py", "modified")
    state = _make_state(repo_path=str(tmp_path), code_changes=[cc])

    with patch(
        "app.agents.nodes.scout_changes._get_git_file_content",
        return_value=old_source,
    ):
        result = scout_changes(state)

    elem = result["change_elements"][0]
    assert "get_date" in elem["elements"]
    assert "/today" in elem["elements"]
    assert "get_date" in elem["old_elements"]
    assert "/date" in elem["old_elements"]


# Tests that deleted files get old_elements from base commit via git show.
def test_scout_changes_deleted_extracts_old_elements():
    old_source = textwrap.dedent("""\
        class LegacyHandler:
            pass

        def handle_legacy():
            pass
    """)

    cc = _make_code_change("src/legacy.py", "deleted")
    state = _make_state(code_changes=[cc])

    with patch(
        "app.agents.nodes.scout_changes._get_git_file_content",
        return_value=old_source,
    ):
        result = scout_changes(state)

    elem = result["change_elements"][0]
    assert elem["elements"] == []
    assert elem["old_elements"] == ["LegacyHandler", "handle_legacy"]


# Tests that if git show fails for a deleted file, old_elements is empty and no exception is raised.
def test_scout_changes_deleted_git_show_fails():
    cc = _make_code_change("src/gone.py", "deleted")
    state = _make_state(code_changes=[cc])

    with patch(
        "app.agents.nodes.scout_changes._get_git_file_content",
        return_value=None,
    ):
        result = scout_changes(state)

    elem = result["change_elements"][0]
    assert elem["elements"] == []
    assert elem["old_elements"] == []


# Tests that non-Python files are skipped even when is_code is True (MVP constraint)
def test_scout_changes_filters_non_python():
    changes = [
        _make_code_change("app.js"),
        _make_code_change("README.txt"),
    ]
    state = _make_state(code_changes=changes)

    result = scout_changes(state)

    assert result["change_elements"] == []


# Tests that malformed Python code doesn't crash the node and produces empty elements.
def test_scout_changes_handles_syntax_error(tmp_path):
    py_file = tmp_path / "bad.py"
    py_file.write_text("def broken(:\n")

    cc = _make_code_change("bad.py", "modified")
    state = _make_state(repo_path=str(tmp_path), code_changes=[cc])

    with patch(
        "app.agents.nodes.scout_changes._get_git_file_content",
        return_value=None,
    ):
        result = scout_changes(state)

    assert len(result["change_elements"]) == 1
    assert result["change_elements"][0]["elements"] == []


# Tests that a file missing from disk doesn't crash the node and produces empty elements.
def test_scout_changes_handles_missing_file(tmp_path):
    cc = _make_code_change("does_not_exist.py", "modified")
    state = _make_state(repo_path=str(tmp_path), code_changes=[cc])

    result = scout_changes(state)

    assert len(result["change_elements"]) == 1
    assert result["change_elements"][0]["elements"] == []
    assert result["change_elements"][0]["old_elements"] == []


# Tests that no code changes in the DB returns an empty change_elements list.
def test_scout_changes_empty_code_changes():
    state = _make_state(code_changes=[])

    result = scout_changes(state)

    assert result == {"change_elements": []}


# Tests that route strings from @app.route('/path') decorators are extracted.
def test_scout_changes_extracts_flask_routes(tmp_path):
    source = textwrap.dedent("""\
        from flask import Flask
        app = Flask(__name__)

        @app.route('/today')
        def get_date():
            return "today"

        @app.route('/users', methods=['GET'])
        def list_users():
            return []
    """)
    py_file = tmp_path / "routes.py"
    py_file.write_text(source)

    cc = _make_code_change("routes.py", "added")
    state = _make_state(repo_path=str(tmp_path), code_changes=[cc])

    result = scout_changes(state)

    elements = result["change_elements"][0]["elements"]
    assert "get_date" in elements
    assert "/today" in elements
    assert "list_users" in elements
    assert "/users" in elements


# Tests that route strings from @router.get('/path') and @router.post('/path') decorators are extracted.
def test_scout_changes_extracts_fastapi_routes(tmp_path):
    source = textwrap.dedent("""\
        from fastapi import APIRouter
        router = APIRouter()

        @router.get('/items')
        async def get_items():
            return []

        @router.post('/items')
        async def create_item():
            return {}
    """)
    py_file = tmp_path / "api.py"
    py_file.write_text(source)

    cc = _make_code_change("api.py", "added")
    state = _make_state(repo_path=str(tmp_path), code_changes=[cc])

    result = scout_changes(state)

    elements = result["change_elements"][0]["elements"]
    assert "get_items" in elements
    assert "/items" in elements
    assert "create_item" in elements


# Tests that non-route decorators don't crash or produce false route elements.
def test_scout_changes_non_route_decorators_safe(tmp_path):
    source = textwrap.dedent("""\
        def login_required(f):
            return f

        @login_required
        def secret_page():
            pass
    """)
    py_file = tmp_path / "views.py"
    py_file.write_text(source)

    cc = _make_code_change("views.py", "added")
    state = _make_state(repo_path=str(tmp_path), code_changes=[cc])

    result = scout_changes(state)

    elements = result["change_elements"][0]["elements"]
    assert elements == ["login_required", "secret_page"]


# Tests that code changes with is_ignored=True are excluded from processing
def test_scout_changes_skips_ignored_files(tmp_path):
    source = textwrap.dedent("""\
        def important_function():
            pass
    """)
    py_file = tmp_path / "src" / "service.py"
    py_file.parent.mkdir(parents=True)
    py_file.write_text(source)

    ignored_cc = _make_code_change("src/service.py", "modified", is_ignored=True)
    state = _make_state(repo_path=str(tmp_path), code_changes=[ignored_cc])

    result = scout_changes(state)

    assert result["change_elements"] == []


# Tests that only non-ignored files are processed when mixed with ignored ones
def test_scout_changes_processes_non_ignored_only(tmp_path):
    source = textwrap.dedent("""\
        def kept_function():
            pass
    """)
    py_file = tmp_path / "src" / "kept.py"
    py_file.parent.mkdir(parents=True)
    py_file.write_text(source)

    kept_cc = _make_code_change("src/kept.py", "modified", is_ignored=False)
    ignored_cc = _make_code_change("tests/test_kept.py", "modified", is_ignored=True)
    state = _make_state(repo_path=str(tmp_path), code_changes=[kept_cc, ignored_cc])

    result = scout_changes(state)

    assert len(result["change_elements"]) == 1
    assert result["change_elements"][0]["file_path"] == "src/kept.py"
