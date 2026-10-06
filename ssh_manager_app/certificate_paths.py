"""Validation shared by certificate search and deployment dialogs."""
import posixpath
from tkinter import messagebox


def certificate_paths(lines: list[str]) -> list[str]:
    paths = []
    for line in lines:
        if any(ord(char) < 32 or ord(char) == 127 for char in line):
            raise ValueError("Linux-Pfade dürfen keine Steuerzeichen enthalten.")
        path = line.strip()
        if not path:
            continue
        if not path.startswith("/") or ".." in path.split("/"):
            raise ValueError("Bitte absolute Linux-Pfade ohne '..' verwenden, z. B. /etc/ssl/private.")
        paths.append(posixpath.normpath("/" + path.lstrip("/")))
    return list(dict.fromkeys(paths))


def confirm_broad_certificate_paths(parent, paths: list[str], *, search: bool = False) -> bool:
    broad = [path for path in paths if path == "/" or len(path.strip("/").split("/")) == 1]
    if not broad:
        return True
    operation = "Die Suche kann viele Dateien erfassen und lange dauern." if search else "Dateien werden direkt in diesen Systemordnern installiert."
    return messagebox.askyesno(
        "Breite Zertifikatspfade bestätigen",
        "Sehr breite oder systemnahe Pfade:\n" + "\n".join(broad) + "\n\n" + operation + "\nGezieltere Unterordner sind empfehlenswert. Trotzdem fortfahren?",
        parent=parent, icon="warning",
    )
