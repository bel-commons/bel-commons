# -*- coding: utf-8 -*-

from celery import Celery


def create_celery(app):
    """Configures celery instance from application, using its config

    :param flask.Flask app: Flask application instance
    :rtype: celery.Celery
    """
    if hasattr(app, 'celery'):
        return app.celery

    celery = Celery(
        app.import_name,
        broker=app.config['CELERY_BROKER_URL']
    )
    celery.conf.update(app.config)

    app.celery = celery

    return celery
