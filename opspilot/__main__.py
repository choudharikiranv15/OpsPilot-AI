"""Allow running OpsPilot as ``python -m opspilot``."""

from opspilot.cli import app

if __name__ == "__main__":
    app(prog_name="opspilot")
