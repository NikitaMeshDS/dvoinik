import importlib.util
from pathlib import Path


def test_showcase_data_covers_every_template_size_and_segment():
    path = Path(__file__).resolve().parents[1] / "scripts" / "build_showcase.py"
    spec = importlib.util.spec_from_file_location("build_showcase", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    data = module.build()
    assert len(data["records"]) == len(data["templates"]) * len(data["sizes"])
    for record in data["records"].values():
        assert f"{record['id']}|all" in data["insights"]
        for sid in record["scenario"]["population"]:
            assert f"{record['id']}|{sid}" in data["insights"]
    senior = data["records"]["senior_deposit|200"]["report"]
    assert [senior[v]["yes"] for v in "ABC"] == [9, 86, 111]
