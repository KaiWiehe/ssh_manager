import csv
from pathlib import Path

from ssh_manager_app.exports import write_csv_export
from ssh_manager_app.models import Session
import pytest
from unittest.mock import patch
from ssh_manager_app.certificate_paths import certificate_paths, confirm_broad_certificate_paths


def test_csv_safe_covers_folder_and_cells_and_raw_preserves_data(tmp_path):
    session = Session("s", "=HYPERLINK(\"bad\")", [], "host")
    for safe in (True, False):
        target = tmp_path / f"{safe}.csv"
        write_csv_export(target, [("@folder", [session])], ["display_name", "notes"], lambda _: " \t+bad", excel_safe=safe)
        with target.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.reader(stream, delimiter=";"))
        assert rows[0] == [("'" if safe else "") + "@folder"]
        assert rows[2] == [("'" if safe else "") + session.display_name, ("'" if safe else "") + " \t+bad"]


@pytest.mark.parametrize("path", ["etc/ssl", "/etc/../root", "/etc/ssl\x00", "/etc/ssl\t", "/etc\r/ssl"])
def test_certificate_paths_reject_unsafe_inputs(path):
    with pytest.raises(ValueError):
        certificate_paths([path])


def test_paths_normalized_broad_paths_require_confirmation():
    assert certificate_paths([" /etc//ssl/./private/ ", "/etc/ssl/private"]) == ["/etc/ssl/private"]
    with patch("ssh_manager_app.certificate_paths.messagebox.askyesno", return_value=False) as ask:
        assert confirm_broad_certificate_paths(None, ["/etc/ssl/private"])
        ask.assert_not_called()
        assert not confirm_broad_certificate_paths(None, ["/etc"], search=True)
        assert "Suche" in ask.call_args.args[1]
