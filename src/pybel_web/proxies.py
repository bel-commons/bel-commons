# -*- coding: utf-8 -*-

from flask import current_app
from werkzeug.local import LocalProxy

from .application_utils import get_manager, get_user_datastore


def get_manager_proxy():
    """Gets a proxy for the manager in the current app

    :rtype: pybel.manager.Manager
    """
    return LocalProxy(lambda: get_manager(current_app))


def get_userdatastore_proxy():
    """Gets a proxy for the user datastore from the current app

    :rtype: flask_security.SQLAlchemyUserDataStore
    """
    return LocalProxy(lambda: get_user_datastore(current_app))


manager = get_manager_proxy()
user_datastore = get_userdatastore_proxy()
