import argparse
import json
from pathlib import Path

from app.gridsfm_case_tools import write_diagnostic_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose a PowerModels JSON case for GridSFM AC handoff blockers.")
    parser.add_argument("case_path", type=Path)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    result = write_diagnostic_report(args.case_path, args.output_dir)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
