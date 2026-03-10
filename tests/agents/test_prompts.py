from app.agents.prompts import (
    get_rewrite_system_prompt,
    build_doc_gen_plan_user_prompt,
    build_doc_gen_rewrite_prompt,
    build_deep_analyze_user_prompt,
    build_doc_updates_summary_prompt,
    DOC_GEN_REWRITE_PROMPTS,
)


# =========== get_rewrite_system_prompt Tests ===========


# Tests that None style defaults to the professional rewrite prompt.
def test_returns_professional_prompt_by_default():
    result = get_rewrite_system_prompt(None)
    assert result == DOC_GEN_REWRITE_PROMPTS["professional"]


# Tests that each known style key returns its corresponding prompt.
def test_returns_prompt_for_known_style():
    for style in ("concise", "descriptive", "professional", "technical"):
        result = get_rewrite_system_prompt(style)
        assert result == DOC_GEN_REWRITE_PROMPTS[style]


# Tests that an unknown style falls back to the professional prompt.
def test_unknown_style_falls_back_to_professional():
    result = get_rewrite_system_prompt("medieval_scroll")
    assert result == DOC_GEN_REWRITE_PROMPTS["professional"]


# Tests that style matching is case-insensitive.
def test_style_matching_is_case_insensitive():
    result = get_rewrite_system_prompt("CONCISE")
    assert result == DOC_GEN_REWRITE_PROMPTS["concise"]


# Tests that passing no policies returns the base prompt unchanged.
def test_no_policies_returns_base_prompt_unchanged():
    result = get_rewrite_system_prompt("professional", docs_policies=None)
    assert result == DOC_GEN_REWRITE_PROMPTS["professional"]
    assert "Documentation Policies" not in result


# Tests that passing policies appends the documentation policies block to the prompt.
def test_with_policies_appends_policies_block():
    policies = "- Use present tense.\n- Keep it concise."
    result = get_rewrite_system_prompt("professional", docs_policies=policies)

    assert result.startswith(DOC_GEN_REWRITE_PROMPTS["professional"])
    assert "## Repository Documentation Policies" in result
    assert "MUST be followed" in result
    assert policies in result


# Tests that docs_policies are appended correctly for every available style.
def test_with_policies_works_for_every_style():
    policies = "Always use active voice."
    for style in ("concise", "descriptive", "professional", "technical"):
        result = get_rewrite_system_prompt(style, docs_policies=policies)
        assert DOC_GEN_REWRITE_PROMPTS[style] in result
        assert policies in result


# =========== build_doc_gen_plan_user_prompt Tests ===========


_FILES = ["docs/api.md", "docs/auth.md"]
_FINDINGS = [
    {
        "code_path": "app/auth.py",
        "drift_type": "outdated_docs",
        "explanation": "Endpoint path changed",
        "matched_doc_paths": ["docs/auth.md"],
    }
]


# Tests that the prompt contains all available documentation file paths.
def test_plan_prompt_contains_file_list():
    result = build_doc_gen_plan_user_prompt(_FILES, _FINDINGS)
    assert "docs/api.md" in result
    assert "docs/auth.md" in result


# Tests that the prompt contains all drift finding details.
def test_plan_prompt_contains_findings():
    result = build_doc_gen_plan_user_prompt(_FILES, _FINDINGS)
    assert "app/auth.py" in result
    assert "outdated_docs" in result
    assert "Endpoint path changed" in result


# Tests that no policies block or compliance line appears when docs_policies is None.
def test_plan_prompt_no_policies_omits_policies_block():
    result = build_doc_gen_plan_user_prompt(_FILES, _FINDINGS, docs_policies=None)
    assert "Documentation Policies" not in result
    assert "comply with" not in result


# Tests that the policies block and compliance line are included when docs_policies is set.
def test_plan_prompt_with_policies_includes_policies_block():
    policies = "- Use present tense.\n- No passive voice."
    result = build_doc_gen_plan_user_prompt(_FILES, _FINDINGS, docs_policies=policies)

    assert "## Documentation Policies" in result
    assert policies in result
    assert "comply with the Documentation Policies" in result


# Tests that the compliance reminder line is absent when no policies are provided.
def test_plan_prompt_compliance_line_absent_when_no_policies():
    result = build_doc_gen_plan_user_prompt(_FILES, _FINDINGS, docs_policies=None)
    assert "comply with the Documentation Policies" not in result


# Tests that all findings are included in the prompt when multiple are provided.
def test_plan_prompt_multiple_findings_all_included():
    findings = [
        {
            "code_path": f"app/module{i}.py",
            "drift_type": "missing_docs",
            "explanation": f"Missing docs for module {i}",
            "matched_doc_paths": [],
        }
        for i in range(3)
    ]
    result = build_doc_gen_plan_user_prompt(_FILES, findings)
    for i in range(3):
        assert f"app/module{i}.py" in result


# Tests that the prompt is still built correctly when no findings are provided.
def test_plan_prompt_empty_findings_still_builds():
    result = build_doc_gen_plan_user_prompt(_FILES, [])
    assert "## Available Documentation Files" in result
    assert "## Drift Findings" in result


# Tests that findings with missing keys use safe default values.
def test_plan_prompt_finding_with_missing_fields_uses_defaults():
    # Finding with no keys — all .get() defaults should kick in
    result = build_doc_gen_plan_user_prompt(_FILES, [{}])
    assert "?" in result  # code_path and drift_type default to "?"
    assert "N/A" in result  # explanation defaults to "N/A"


# Tests that sections appear in the correct order: files, policies, findings.
def test_plan_prompt_sections_appear_in_correct_order():
    policies = "Use active voice."
    result = build_doc_gen_plan_user_prompt(_FILES, _FINDINGS, docs_policies=policies)
    files_pos = result.index("## Available Documentation Files")
    policies_pos = result.index("## Documentation Policies")
    findings_pos = result.index("## Drift Findings")
    assert files_pos < policies_pos < findings_pos


# Tests that multiple findings are numbered sequentially in the prompt.
def test_plan_prompt_findings_numbered_sequentially():
    findings = [
        {
            "code_path": f"app/m{i}.py",
            "drift_type": "outdated_docs",
            "explanation": "changed",
            "matched_doc_paths": [],
        }
        for i in range(3)
    ]
    result = build_doc_gen_plan_user_prompt(_FILES, findings)
    assert "1." in result
    assert "2." in result
    assert "3." in result


# Tests that the prompt instructs the LLM not to invent or guess file paths.
def test_plan_prompt_instructs_not_to_hallucinate_paths():
    result = build_doc_gen_plan_user_prompt(_FILES, _FINDINGS)
    assert "Do NOT invent or guess file paths" in result


# =========== build_deep_analyze_user_prompt TESTS ===========


# Tests that the code path and change type appear in the deep analyze prompt.
def test_deep_analyze_contains_code_path():
    result = build_deep_analyze_user_prompt(
        code_path="app/routes/auth.py",
        change_type="modified",
        elements=["login", "logout"],
        old_elements=["sign_in"],
        diff="- def sign_in\n+ def login",
        matched_doc_snippets="## Auth\nSign in using /auth/signin",
    )
    assert "app/routes/auth.py" in result
    assert "modified" in result


# Tests that new code elements appear in the deep analyze prompt.
def test_deep_analyze_contains_elements():
    result = build_deep_analyze_user_prompt(
        code_path="app/api.py",
        change_type="added",
        elements=["create_user", "UserController"],
        old_elements=[],
        diff="+class UserController",
        matched_doc_snippets="",
    )
    assert "create_user" in result
    assert "UserController" in result


# Tests that the git diff is included verbatim in the deep analyze prompt.
def test_deep_analyze_contains_diff():
    diff = "-old_function()\n+new_function()"
    result = build_deep_analyze_user_prompt(
        code_path="app/api.py",
        change_type="modified",
        elements=[],
        old_elements=[],
        diff=diff,
        matched_doc_snippets="",
    )
    assert diff in result


# Tests that matched documentation snippets are included in the deep analyze prompt.
def test_deep_analyze_contains_doc_snippets():
    snippet = "## Endpoints\n`GET /users` - returns all users"
    result = build_deep_analyze_user_prompt(
        code_path="app/api.py",
        change_type="modified",
        elements=[],
        old_elements=[],
        diff="",
        matched_doc_snippets=snippet,
    )
    assert snippet in result


# Tests that old (removed) code elements appear in the deep analyze prompt.
def test_deep_analyze_contains_old_elements():
    result = build_deep_analyze_user_prompt(
        code_path="app/api.py",
        change_type="modified",
        elements=["new_fn"],
        old_elements=["old_fn", "removed_fn"],
        diff="",
        matched_doc_snippets="",
    )
    assert "old_fn" in result
    assert "removed_fn" in result


# Tests that the deep analyze prompt renders correctly with empty elements and diff.
def test_deep_analyze_empty_elements_still_renders():
    result = build_deep_analyze_user_prompt(
        code_path="app/api.py",
        change_type="deleted",
        elements=[],
        old_elements=[],
        diff="",
        matched_doc_snippets="",
    )
    assert "## Code Change" in result
    assert "Git Diff" in result


# =========== build_doc_gen_rewrite_prompt TESTS ===========


# Tests that the doc file path appears in the rewrite prompt.
def test_rewrite_prompt_contains_doc_path():
    result = build_doc_gen_rewrite_prompt(
        doc_path="docs/api.md",
        current_content="# API\nOld content",
        change_descriptions=["Update auth endpoint"],
    )
    assert "docs/api.md" in result


# Tests that the current file content is included as is in the rewrite prompt.
def test_rewrite_prompt_contains_current_content():
    content = "# API\nSome existing documentation"
    result = build_doc_gen_rewrite_prompt(
        doc_path="docs/api.md",
        current_content=content,
        change_descriptions=["Update endpoint"],
    )
    assert content in result


# Tests that all change descriptions appear in the rewrite prompt.
def test_rewrite_prompt_contains_all_change_descriptions():
    descriptions = ["Update login route", "Remove deprecated param", "Add response schema"]
    result = build_doc_gen_rewrite_prompt(
        doc_path="docs/api.md",
        current_content="# API",
        change_descriptions=descriptions,
    )
    for desc in descriptions:
        assert desc in result


# Tests that change descriptions are formatted as bullet points.
def test_rewrite_prompt_formats_descriptions_as_bullets():
    result = build_doc_gen_rewrite_prompt(
        doc_path="docs/api.md",
        current_content="# API",
        change_descriptions=["First change", "Second change"],
    )
    assert "- First change" in result
    assert "- Second change" in result


# Tests that a single change description is rendered correctly as a bullet.
def test_rewrite_prompt_single_description():
    result = build_doc_gen_rewrite_prompt(
        doc_path="docs/readme.md",
        current_content="# Readme",
        change_descriptions=["Fix typo in intro"],
    )
    assert "- Fix typo in intro" in result
    assert "docs/readme.md" in result


# Tests that the rewrite prompt renders all sections even with no change descriptions.
def test_rewrite_prompt_empty_descriptions_renders():
    result = build_doc_gen_rewrite_prompt(
        doc_path="docs/api.md",
        current_content="# API",
        change_descriptions=[],
    )
    assert "## Document to Update" in result
    assert "### Required Changes" in result


# =========== build_doc_updates_summary_prompt TESTS ===========


# Tests that the doc file path is included in the summary prompt.
def test_summary_prompt_contains_doc_path():
    result = build_doc_updates_summary_prompt(
        [
            {"doc_path": "docs/api.md", "descriptions": ["Updated auth section"]},
        ]
    )
    assert "docs/api.md" in result


# Tests that all change descriptions are included in the summary prompt.
def test_summary_prompt_contains_descriptions():
    result = build_doc_updates_summary_prompt(
        [
            {"doc_path": "docs/api.md", "descriptions": ["Updated route", "Removed param"]},
        ]
    )
    assert "Updated route" in result
    assert "Removed param" in result


# Tests that multiple descriptions for one file are joined with a semicolon.
def test_summary_prompt_joins_multiple_descriptions_with_semicolon():
    result = build_doc_updates_summary_prompt(
        [
            {"doc_path": "docs/api.md", "descriptions": ["Change A", "Change B"]},
        ]
    )
    assert "Change A; Change B" in result


# Tests that all file paths are included when multiple files are summarised.
def test_summary_prompt_multiple_files_all_included():
    file_changes = [
        {"doc_path": "docs/api.md", "descriptions": ["Updated endpoints"]},
        {"doc_path": "docs/auth.md", "descriptions": ["Added OAuth section"]},
        {"doc_path": "docs/setup.md", "descriptions": ["Updated install steps"]},
    ]
    result = build_doc_updates_summary_prompt(file_changes)
    assert "docs/api.md" in result
    assert "docs/auth.md" in result
    assert "docs/setup.md" in result


# Tests that the summary prompt renders the intro sentence even with an empty file list.
def test_summary_prompt_empty_list_still_renders():
    result = build_doc_updates_summary_prompt([])
    assert "following documentation files" in result


# Tests that a single description does not produce a spurious semicolon in the output.
def test_summary_prompt_single_description_no_semicolon():
    result = build_doc_updates_summary_prompt(
        [
            {"doc_path": "docs/api.md", "descriptions": ["Only one change"]},
        ]
    )
    assert ";" not in result
    assert "Only one change" in result
