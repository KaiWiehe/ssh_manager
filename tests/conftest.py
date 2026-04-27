import sys
import types


if "winreg" not in sys.modules:
    def _not_available(*args, **kwargs):
        raise OSError("winreg is not available on this platform")

    winreg_stub = types.SimpleNamespace(
        HKEY_CURRENT_USER=object(),
        REG_SZ=1,
        REG_DWORD=2,
        OpenKey=_not_available,
        EnumKey=_not_available,
        QueryValueEx=_not_available,
    )
    sys.modules["winreg"] = winreg_stub
