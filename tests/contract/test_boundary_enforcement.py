"""Static Plane Boundary Enforcement Tests.

Verifies using AST analysis that src/control_plane and src/data_plane modules
never import across plane boundaries.
"""

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CONTROL_PLANE_DIR = REPO_ROOT / "src" / "control_plane"
DATA_PLANE_DIR = REPO_ROOT / "src" / "data_plane"


def _check_forbidden_imports(target_dir: Path, forbidden_prefixes: tuple[str, ...]) -> list[str]:
    violations = []

    for py_file in target_dir.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except SyntaxError as e:
            violations.append(f"Syntax error in {py_file}: {e}")
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith(forbidden_prefixes):
                        violations.append(
                            f"[{py_file.relative_to(REPO_ROOT)}:{node.lineno}] "
                            f"Forbidden import '{alias.name}'"
                        )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                # Check root module path (e.g., 'from src.data_plane import worker')
                if module.startswith(forbidden_prefixes):
                    violations.append(
                        f"[{py_file.relative_to(REPO_ROOT)}:{node.lineno}] "
                        f"Forbidden import from '{module}'"
                    )
                else:
                    # Check imported aliases (e.g., 'from src import data_plane')
                    for alias in node.names:
                        full_import = f"{module}.{alias.name}" if module else alias.name
                        is_forbidden = (
                            full_import.startswith(forbidden_prefixes)
                            or alias.name in forbidden_prefixes
                        )
                        if is_forbidden:
                            violations.append(
                                f"[{py_file.relative_to(REPO_ROOT)}:{node.lineno}] "
                                f"Forbidden import of symbol '{alias.name}' from '{module or '.'}'"
                            )

    return violations


@pytest.mark.unit
def test_no_cross_plane_imports_in_control_plane():
    """Verify that src/control_plane/ contains ZERO direct imports of src.data_plane."""
    violations = _check_forbidden_imports(CONTROL_PLANE_DIR, ("src.data_plane", "data_plane"))
    assert not violations, "Control Plane boundary violation(s) found:\n" + "\n".join(violations)


@pytest.mark.unit
def test_no_cross_plane_imports_in_data_plane():
    """Verify that src/data_plane/ contains ZERO direct imports of src.control_plane."""
    violations = _check_forbidden_imports(DATA_PLANE_DIR, ("src.control_plane", "control_plane"))
    assert not violations, "Data Plane boundary violation(s) found:\n" + "\n".join(violations)
