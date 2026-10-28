"""Keep the device credential outside source, config files, and browser storage."""

SERVICE = "AcademiaShieldDevice"
ACCOUNT = "device"


def load_credential():
    try:
        import keyring
        return keyring.get_password(SERVICE, ACCOUNT)
    except Exception:
        return None


def save_credential(value):
    import keyring
    keyring.set_password(SERVICE, ACCOUNT, value)


def clear_credential():
    import keyring
    try:
        keyring.delete_password(SERVICE, ACCOUNT)
    except keyring.errors.PasswordDeleteError:
        pass


def device_id():
    value = load_credential()
    return value.split(".", 1)[0] if value and "." in value else None
