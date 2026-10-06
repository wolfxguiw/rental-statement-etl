"""Desktop application entry point used by the Windows build."""

import argparse

from alugueis_extrator.gui import main


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--automation-folder", help=argparse.SUPPRESS)
    parser.add_argument("--automation-competence", help=argparse.SUPPRESS)
    parser.add_argument("--automation-run", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--automation-close", action="store_true", help=argparse.SUPPRESS)
    automation_args, _ = parser.parse_known_args()
    main(
        initial_folder=automation_args.automation_folder,
        initial_competence=automation_args.automation_competence,
        automation_run=automation_args.automation_run,
        automation_close=automation_args.automation_close,
    )
