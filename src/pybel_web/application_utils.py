def get_scai_role(app):
    """Gets the SCAI role from the Flask app

    :param flask.Flask app:
    :rtype: Role
    """
    return get_pybel(app).scai_role


def get_sentry(app):
    """Gets the User Data Store from a Flask app

    :param flask.Flask app: A Flask app
    :rtype: raven.Sentry
    """
    return get_pybel(app).sentry


def get_user_datastore(app):
    """Gets the User Data Store from a Flask app

    :param flask.Flask app: A Flask app
    :rtype: flask_security.DatabaseService
    """
    return get_pybel(app).user_datastore


def get_api(app):
    """Gets the dictionary service from a Flask app

    :param flask.Flask app: A Flask app
    :rtype: DatabaseService
    """
    return get_pybel(app).api


def get_manager(app):
    """Gets the cache manger from a Flask app

    :param flask.Flask app: A Flask app
    :rtype: pybel.manager.cache.Manager
    """
    return get_pybel(app).manager


def get_pybel(app):
    """
    :param flask.Flask app: A Flask app
    :rtype: web.application._FlaskPybelState
    """
    if 'pybel' not in app.extensions:
        raise ValueError

    return app.extensions['pybel']