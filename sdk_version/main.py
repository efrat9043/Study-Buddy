"""Study Buddy (SDK version) - command-line entry point.

Usage:
    python sdk_version/main.py <file.txt>   read the material from a file
    python sdk_version/main.py              paste the material, then Ctrl+Z and Enter
"""

import json
import sys

from study_buddy_sdk import StudyBuddyError, run_agent


def read_study_material() -> str:
    """Read the material from the file given as an argument, or from pasted text."""
    if len(sys.argv) > 1:
        path = sys.argv[1]
        try:
            with open(path, encoding="utf-8") as file:
                return file.read()
        except (OSError, UnicodeDecodeError) as error:
            raise StudyBuddyError(f"Could not read the file '{path}': {error}")

    print("Paste the study material, then press Ctrl+Z and Enter:")
    return sys.stdin.read()


def main() -> None:
    try:
        study_text = read_study_material().strip()
        if not study_text:
            raise StudyBuddyError("No study material was provided.")
        result = run_agent(study_text)
    except StudyBuddyError as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
