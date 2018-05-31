# -*- coding: utf-8 -*-

"""Local proxies for PyBEL Web."""

from flask import current_app
from werkzeug.local import LocalProxy

from .application_utils import FlaskPyBEL

__all__ = [
    'manager',
]


def get_manager_proxy():
    """Get a proxy for the manager in the current app.

    Why make this its own function? It tricks type assertion tools into knowing that the LocalProxy object represents
    a WebManager.

    :rtype: pybel_web.manager.WebManager
    """
    return LocalProxy(lambda: FlaskPyBEL.get_state(current_app).manager)


manager = get_manager_proxy()
