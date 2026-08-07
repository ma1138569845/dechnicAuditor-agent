"""Manual end-to-end verification for run_office_cli_command.

Run with: python tests/manual_verify_office_cli.py
"""
import os
import sys
import tempfile

# Make the project root importable when running this script directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.office_cli_tool import run_office_cli_command


def main():
    # ignore_cleanup_errors avoids Windows PermissionError when officecli's
    # resident mode still holds the file handle as the temp dir is removed.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        docx = os.path.join(d, "test.docx")

        r1 = run_office_cli_command("officecli create " + docx)
        print("create success:", r1["success"], "exit:", r1["exit_code"])
        if not r1["success"]:
            print("  stderr:", r1["stderr"][:300])
            return

        r2 = run_office_cli_command(
            "officecli add " + docx + " /body --type paragraph --prop text=HelloWorld"
        )
        print("add success:", r2["success"], "exit:", r2["exit_code"])
        if not r2["success"]:
            print("  stderr:", r2["stderr"][:300])
            return

        r3 = run_office_cli_command("officecli view " + docx + " text")
        print("view success:", r3["success"], "exit:", r3["exit_code"])
        print("view stdout:", r3["stdout"][:200])

        # Release officecli's resident session so the file handle closes before
        # the temp directory is removed.
        run_office_cli_command("officecli close " + docx)

        assert "HelloWorld" in r3["stdout"], "text not found in view output"
        print("\nEND-TO-END OK: officecli create/add/view all succeeded")


if __name__ == "__main__":
    main()
