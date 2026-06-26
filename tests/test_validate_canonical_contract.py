from cipp_contracts.normalize.build_canonical_contract import build_template
from cipp_contracts.validate.validate_canonical_contract import validate


def test_template_is_valid_enough_for_project_start() -> None:
    data = build_template("reference_001")
    issues = validate(data)
    blocking = [issue for issue in issues if issue.severity in {"error", "critical"}]
    assert blocking == []


def test_duplicate_precedence_rank_is_error() -> None:
    data = build_template("reference_001")
    data["documents"][0]["precedence_rank"] = 1
    data["documents"][1]["precedence_rank"] = 1
    issues = validate(data)
    assert any(issue.issue_type == "duplicate_precedence_rank" for issue in issues)

