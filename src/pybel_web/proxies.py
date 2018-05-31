# -*- coding: utf-8 -*-

from flask import current_app
from werkzeug.local import LocalProxy

from .application_utils import get_manager

__all__ = [
    'manager',
]


def get_manager_proxy():
    """Gets a proxy for the manager in the current app

    :rtype: pybel_web.manager.WebManager
    """
    return LocalProxy(lambda: get_manager(current_app))


manager = get_manager_proxy()
