import json

from ccc.testing.harness import harness_registry, run_harness, write_harness_results


def test_harness_has_exactly_h01_through_h62_and_preserves_unspecified():
    registry = harness_registry()
    assert [item["harness_id"] for item in registry] == [f"H{i:02d}" for i in range(1, 63)]
    assert all("historical_meaning" in item for item in registry)
    assert any(item["expected_result"] == "UNSPECIFIED" for item in registry)


def test_harness_results_are_machine_readable_and_do_not_promote_unspecified():
    result = run_harness()
    assert result["total"] == 62
    assert result["failed"] == 0
    assert result["errors"] == 0
    assert result["passed"] == 44
    assert result["unspecified"] == 18
    assert result["passed"] + result["failed"] + result["errors"] + result["skipped"] + result["unspecified"] == result["total"]
    assert all(item["status"] != "PASS" for item in result["records"] if item["expected_result"] == "UNSPECIFIED")


def test_harness_results_can_be_written(tmp_path):
    path = write_harness_results(tmp_path / "harness.json")
    data = json.loads(path.read_text())
    assert data["total"] == 62
    assert len(data["records"]) == 62
