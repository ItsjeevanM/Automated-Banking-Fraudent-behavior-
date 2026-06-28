from pathlib import Path
from services import pdfreader, ocr_module_local

UPLOAD_DIR = Path("uploads")

def route(input_path: Path) -> Path:
    suffix = Path(input_path).suffix.lower()

    if suffix == ".csv":
        return Path(input_path)                      # already a CSV, pass through as-is

    if suffix == ".pdf":
        return Path(pdfreader.convert(input_path, UPLOAD_DIR))

    if suffix in (".jpg", ".jpeg", ".png"):
        return Path(ocr_module_local.convert(input_path, UPLOAD_DIR))

    raise ValueError(f"Unsupported file type: {suffix}")