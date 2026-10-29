import importlib.util
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[3]


def test_deploy_scan_includes_dictionary_runtime_files():
    path = ROOT / "scripts" / "deploy_ea_skills.py"
    spec = importlib.util.spec_from_file_location("deploy_ea_skills", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    files = module.walk(ROOT / "tools")
    assert "energy_audit/dept_dict.py" in files
    assert "energy_audit/db_config.py" in files
    assert "energy_audit/_paths.py" in files
    assert "energy_audit/indicators.py" in files
    assert "energy_audit/institution_classifier.py" in files
    assert "energy_audit/file_resolver.py" in files


def test_source_tree_imports_the_collection_chain():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    result = subprocess.run(
        [sys.executable, "-c", "import tools.energy_audit.pg_collector"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert result.returncode == 0, result.stderr


def test_tools_packages_preserve_production_import_surface():
    import tools.energy_audit
    from tools import check_file_requirements

    assert callable(check_file_requirements)
    assert tools.energy_audit.__all__ == [
        "ExcelDataProcessor",
        "PgDataQuery",
        "RAGKnowledgeRetrieval",
        "ReportGenerator",
    ]

