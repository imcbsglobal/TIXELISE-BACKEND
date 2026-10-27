import threading

_local = threading.local()


def set_correlation_id(value):
    _local.correlation_id = value


def get_correlation_id():
    return getattr(_local, "correlation_id", None)


def set_tenant_context(tenant_id, role=None, user_id=None):
    _local.tenant_id = tenant_id
    _local.role = role
    _local.user_id = user_id


def get_current_tenant_id():
    return getattr(_local, "tenant_id", None)


def get_current_role():
    return getattr(_local, "role", None)


def get_current_user_id():
    return getattr(_local, "user_id", None)


def clear_tenant_context():
    _local.tenant_id = None
    _local.role = None
    _local.user_id = None
