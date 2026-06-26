from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MAX_REPORT_CHARS = 1500

SKIP_DIRS = {
    ".git",
    ".venv",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
}

CODE_EXTS = {
    ".py",
    ".sql",
    ".ps1",
    ".sh",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".html",
    ".css",
}

DOC_EXTS = {".md", ".txt", ".rst"}
DATA_DIRS = {"data"}


def iter_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        if path.is_file():
            files.append(path)
    return files


def human_size(size: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{size} B"


def source_lines(path: Path) -> int:
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return 0

    count = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("#", "--", "//")):
            continue
        count += 1
    return count


def count_project_scripts() -> int:
    pyproject = ROOT / "pyproject.toml"
    if not pyproject.exists():
        return 0

    in_scripts = False
    count = 0
    for line in pyproject.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if stripped == "[project.scripts]":
            in_scripts = True
            continue
        if in_scripts and stripped.startswith("["):
            break
        if in_scripts and stripped and not stripped.startswith("#") and "=" in stripped:
            count += 1
    return count


def main() -> None:
    files = iter_files()
    total_size = sum(path.stat().st_size for path in files)
    by_ext = Counter(path.suffix.lower() or "<ei päätettä>" for path in files)

    code_files = [path for path in files if path.suffix.lower() in CODE_EXTS]
    doc_files = [path for path in files if path.suffix.lower() in DOC_EXTS]
    data_files = [path for path in files if path.relative_to(ROOT).parts[:1] and path.relative_to(ROOT).parts[0] in DATA_DIRS]

    code_lines = sum(source_lines(path) for path in code_files)
    python_modules = sum(1 for path in files if path.suffix.lower() == ".py" and "src" in path.relative_to(ROOT).parts)
    sql_migrations = len(list((ROOT / "db" / "migrations").glob("*.sql")))
    tests = len(list((ROOT / "tests").rglob("test_*.py")))
    project_scripts = count_project_scripts()

    top_exts = ", ".join(f"{ext}:{count}" for ext, count in by_ext.most_common(5))
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    report = f"""REPOSITORION TILANNE
Paivitetty: {timestamp}

Koko: {human_size(total_size)} (ei .git/.venv/valimuistit)
Tiedostot: {len(files)} kpl | data: {len(data_files)} | dokumentit: {len(doc_files)}
Koodi: {len(code_files)} tiedostoa | {code_lines} koodirivia
Moduulit: {python_modules} Python | migraatiot: {sql_migrations} SQL | testit: {tests}
Scriptit: {project_scripts} komentotyokalua pyprojectissa
Yleisimmat paatteet: {top_exts}

Arvio: repo on jasennelty ETL-/tietokantaprojektiksi. Seuraava tarkein kovetus on operatiivisen ops-importerin ja migraation vakiointi."""

    if len(report) > MAX_REPORT_CHARS:
        report = report[: MAX_REPORT_CHARS - 3].rstrip() + "..."

    print(report)


if __name__ == "__main__":
    main()
