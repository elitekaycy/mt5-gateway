"""The promotion gate, and the catalog staying complete as the API grows."""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "attestation"))

from cases import ROUTE_COVERAGE, required_cases  # noqa: E402
from verify import problems_for, record_problems, source_fingerprint  # noqa: E402

RUNNER = (ROOT / "attestation" / "run.py").read_text()


def _app_routes() -> set[str]:
    found = set()
    for path in (ROOT / "app").rglob("*.py"):
        text = path.read_text()
        for route, methods in re.findall(
            r'_bp\.route\("([^"]+)"(?:,\s*methods=\[([^\]]*)\])?', text
        ):
            for method in re.findall(r"[A-Z]+", methods) or ["GET"]:
                found.add(f"{method} {route}")
        for method, route in re.findall(r'_bp\.(get|post|put|delete)\("([^"]+)"', text):
            found.add(f"{method.upper()} {route}")
    return found


def test_every_api_route_has_an_attestation_case():
    assert _app_routes() == set(ROUTE_COVERAGE)


@pytest.mark.parametrize("case", sorted(set(ROUTE_COVERAGE.values())))
def test_route_coverage_names_a_required_case(case):
    assert case in required_cases("headless")


@pytest.mark.parametrize("case", required_cases("headless"))
def test_every_required_case_is_implemented(case):
    assert f"def {case}(" in RUNNER


def test_every_route_the_read_case_claims_is_really_called():
    for route, case in ROUTE_COVERAGE.items():
        if case == "api_every_read_route":
            path = route.split(" ")[1].split("<")[0]
            assert path in RUNNER, route


def test_both_images_need_the_same_catalog():
    assert required_cases("vnc") == required_cases("headless")


def test_the_promise_case_is_required():
    assert "boot_fresh_three_vars_no_servers_dat" in required_cases("vnc")


def _record(variant="headless", fingerprint="abc"):
    return {
        "fingerprint": fingerprint,
        "variant": variant,
        "cases": {name: {"ok": True} for name in required_cases(variant)},
    }


def test_a_complete_passing_record_is_accepted():
    assert record_problems(_record(), "abc", "headless") == []


def test_a_record_for_other_source_is_refused():
    assert "record is for abc" in record_problems(_record(), "def", "headless")[0]


def test_a_record_for_the_other_image_is_refused():
    assert "variant vnc" in record_problems(_record("vnc"), "abc", "headless")[0]


def test_a_failed_case_is_refused():
    record = _record()
    record["cases"]["api_partial_close"]["ok"] = False
    assert record_problems(record, "abc", "headless") == [
        "headless: failed case api_partial_close"
    ]


def test_a_missing_case_is_refused():
    record = _record()
    del record["cases"]["recovery_restart"]
    assert record_problems(record, "abc", "headless") == [
        "headless: missing case recovery_restart"
    ]


def test_a_truthy_non_boolean_result_is_refused():
    record = _record()
    record["cases"]["api_partial_close"]["ok"] = "yes"
    assert record_problems(record, "abc", "headless")


@pytest.fixture
def repo(tmp_path):
    def git(*args):
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

    (tmp_path / "app").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "app" / "a.py").write_text("one")
    (tmp_path / "docs" / "d.md").write_text("doc")
    (tmp_path / "VERSION").write_text("1")
    (tmp_path / "Dockerfile").write_text("FROM x")
    git("init", "-q")
    git("add", ".")
    git("commit", "-qm", "x")
    return tmp_path


def test_runtime_code_changes_the_fingerprint(repo):
    before = source_fingerprint(repo)
    (repo / "app" / "a.py").write_text("two")
    assert source_fingerprint(repo) != before


def test_the_dockerfile_changes_the_fingerprint(repo):
    before = source_fingerprint(repo)
    (repo / "Dockerfile").write_text("FROM y")
    assert source_fingerprint(repo) != before


def test_docs_and_version_do_not_change_the_fingerprint(repo):
    before = source_fingerprint(repo)
    (repo / "docs" / "d.md").write_text("new")
    (repo / "VERSION").write_text("2")
    assert source_fingerprint(repo) == before


def test_a_new_runtime_file_changes_the_fingerprint(repo):
    before = source_fingerprint(repo)
    (repo / "app" / "b.py").write_text("x")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    assert source_fingerprint(repo) != before


def test_no_records_means_refused(repo):
    problems = problems_for(repo)
    assert len(problems) == 2
    assert "no attestation record" in problems[0]


def test_records_for_both_images_are_accepted(repo):
    fingerprint = source_fingerprint(repo)
    records = repo / "attestation" / "records"
    records.mkdir(parents=True)
    for variant in ("vnc", "headless"):
        path = records / f"{fingerprint}-{variant}.json"
        path.write_text(json.dumps(_record(variant, fingerprint)))
    assert problems_for(repo) == []


def test_only_one_image_attested_is_refused(repo):
    fingerprint = source_fingerprint(repo)
    records = repo / "attestation" / "records"
    records.mkdir(parents=True)
    path = records / f"{fingerprint}-vnc.json"
    path.write_text(json.dumps(_record("vnc", fingerprint)))
    assert len(problems_for(repo)) == 1


def test_promotion_runs_the_gate_before_building_anything():
    workflow = (ROOT / ".github" / "workflows" / "promote-to-main.yml").read_text()
    assert workflow.index("attestation/verify.py") < workflow.index(
        "Build promote branch"
    )


def test_the_broker_secrets_can_never_reach_a_pull_request():
    workflow = (ROOT / ".github" / "workflows" / "attestation.yml").read_text()
    triggers = workflow.split("permissions:")[0]
    assert "workflow_dispatch" in triggers
    assert "pull_request" not in triggers.split("on:")[1]
    assert "max-parallel: 1" in workflow
