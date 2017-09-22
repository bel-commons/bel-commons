from celery import Celery


def create_celery(application):
    """Configures celery instance from application, using its config

    :param flask.Flask application: Flask application instance
    :return: A Celery instance
    :rtype: celery.Celery
    """
    if hasattr(application, 'celery'):
        return application.celery

    celery = Celery(
        application.import_name,
        broker=application.config['CELERY_BROKER_URL']
    )
    celery.conf.update(application.config)
    TaskBase = celery.Task

    class ContextTask(TaskBase):
        """Celery task running within a Flask application context."""
        abstract = True

        def __call__(self, *args, **kwargs):
            with application.app_context():
                return super(ContextTask, self).__call__(*args, **kwargs)

    celery.Task = ContextTask

    application.celery = celery

    return celery
