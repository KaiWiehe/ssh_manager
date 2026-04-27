HKEY_CURRENT_USER = object()
REG_SZ = 1
REG_DWORD = 2


def OpenKey(*args, **kwargs):
    raise OSError("winreg is not available on this platform")


def EnumKey(*args, **kwargs):
    raise OSError("winreg is not available on this platform")


def QueryValueEx(*args, **kwargs):
    raise OSError("winreg is not available on this platform")
