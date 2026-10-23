"""Console entry point. The GUI remains available through ssh_manager.py."""
from ssh_manager_app.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
