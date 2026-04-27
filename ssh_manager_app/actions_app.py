from __future__ import annotations

import tkinter as tk


def show_search_history_menu(app) -> None:
    menu = tk.Menu(app, tearoff=False)
    if app._search_history:
        for item in app._search_history:
            menu.add_command(label=item, command=lambda v=item: app._apply_search_history_entry(v))
        menu.add_separator()
        menu.add_command(label="Verlauf leeren", command=app._clear_search_history)
    else:
        menu.add_command(label="Kein Suchverlauf", state=tk.DISABLED)
    x = app._search_history_btn.winfo_rootx()
    y = app._search_history_btn.winfo_rooty() + app._search_history_btn.winfo_height()
    menu.tk_popup(x, y)



def get_all_folder_names(app) -> list[str]:
    """Gibt alle bekannten Ordnernamen aus allen Session-Quellen zurück."""
    folders = {session.folder_key for session in app._sessions if session.folder_key}
    return sorted(folders)



def get_ssh_aliases(app) -> list[str]:
    """Gibt alle SSH-Config-Aliases zurück (für Alias-Picker im Dialog)."""
    return sorted(session.display_name for session in app._sessions if session.source == "ssh_config")



def export_settings_dialog(app) -> None:
    if app._settings_view is None:
        return
    app._settings_view._export_settings()



def import_settings_dialog(app) -> None:
    if app._settings_view is None:
        return
    app._settings_view._import_settings()



def close_app(app) -> None:
    app._persist_ui_state()
    app.destroy()
