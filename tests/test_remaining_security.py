import csv
from pathlib import Path

from ssh_manager_app.exports import write_csv_export
from ssh_manager_app.models import Session


def test_csv_safe_covers_folder_and_cells_and_raw_preserves_data(tmp_path):
    session = Session("s", "=HYPERLINK(\"bad\")", [], "host")
    for safe in (True, False):
        target = tmp_path / f"{safe}.csv"
        write_csv_export(target, [("@folder", [session])], ["display_name", "notes"], lambda _: " \t+bad", excel_safe=safe)
        with target.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.reader(stream, delimiter=";"))
        assert rows[0] == [("'" if safe else "") + "@folder"]
        assert rows[2] == [("'" if safe else "") + session.display_name, ("'" if safe else "") + " \t+bad"]
