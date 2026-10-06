"""Validated ownership policy and atomic remote certificate installation."""
import re
import shlex

CERTIFICATE_MODES = ("0600", "0640", "0644", "0400", "0440", "0444")


def certificate_owner(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"(?!-)[A-Za-z0-9._-]+", value):
        raise ValueError("Ungültiger Dateibesitzer.")
    return value


def certificate_mode(value: str) -> str:
    if value not in CERTIFICATE_MODES:
        raise ValueError("Zertifikatsrechte müssen 0600, 0640, 0644, 0400, 0440 oder 0444 sein.")
    return value


def certificate_install_prelude(owner: str, apply_to_existing: bool, overwrite: bool) -> list[str]:
    return [
        "file_owner=" + shlex.quote(certificate_owner(owner)),
        "preserve_existing=" + ("0" if apply_to_existing else "1"),
        "overwrite=" + ("1" if overwrite else "0"),
        *r'''
install_tmp=''
install_uid=$(id -u -- "$file_owner") && install_gid=$(id -g -- "$file_owner") || {
  echo "FEHLER: Dateibesitzer existiert auf diesem Server nicht: $file_owner"
  exit 1
}
install_certificate() {
  local source="$1" target="$2" selected_mode="$3" metadata uid gid mode parent
  if sudo test -L "$target"; then
    target=$(sudo readlink -e -- "$target") || { echo 'FEHLER: Defekter Ziel-Symlink'; return 1; }
  fi
  uid="$install_uid"; gid="$install_gid"; mode="$selected_mode"
  if sudo test -e "$target"; then
    if [ "$overwrite" -ne 1 ]; then
      echo "AUSGELASSEN: Zieldatei existiert bereits: $target"
      return 2
    fi
    sudo test -f "$target" || { echo "FEHLER: Ziel ist keine reguläre Datei: $target"; return 1; }
    if [ "$preserve_existing" -eq 1 ]; then
      metadata=$(sudo stat -c '%u %g %a' -- "$target") || return 1
      read -r uid gid mode <<< "$metadata"
    fi
  fi
  parent=$(dirname -- "$target") || return 1
  install_tmp=$(sudo mktemp "$parent/.ssh-manager-cert.XXXXXX") || return 1
  sudo cp -- "$source" "$install_tmp" &&
    sudo chown -- "$uid:$gid" "$install_tmp" &&
    sudo chmod -- "$mode" "$install_tmp" || return 1
  if [ "$overwrite" -eq 1 ]; then
    sudo mv -f -- "$install_tmp" "$target" || return 1
  else
    sudo mv -n -- "$install_tmp" "$target" || return 1
    if sudo test -e "$install_tmp"; then
      echo "AUSGELASSEN: Zieldatei wurde zwischenzeitlich erstellt: $target"
      return 2
    fi
  fi
  install_tmp=''
}
'''.strip().splitlines(),
    ]
