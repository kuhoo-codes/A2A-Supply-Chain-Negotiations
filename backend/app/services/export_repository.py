from pathlib import Path

from backend.app.services.json_store import ensure_directory, write_json


def save_simulation_export(
    exports_dir: Path,
    run_id: str,
    payload: dict,
) -> Path:
    ensure_directory(exports_dir)
    file_path = exports_dir / f"{run_id}-simulation-export.json"
    write_json(file_path, payload)
    return file_path
