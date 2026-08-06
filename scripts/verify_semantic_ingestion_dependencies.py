from __future__ import annotations

import importlib


_REQUIRED_MODULES = (
    "markitdown",
    "mammoth",
    "openpyxl",
    "pandas",
    "pdfminer.high_level",
    "pypdf",
    "pptx",
    "xlrd",
)


def main() -> None:
    for module in _REQUIRED_MODULES:
        importlib.import_module(module)
    print("Semantic ingestion conversion dependencies are available.")


if __name__ == "__main__":
    main()
