# -*- coding: utf-8 -*-

"""A blueprint for receiving uploads of graphs as JSON."""

import logging

from flask import Blueprint, abort, current_app, jsonify, request
from flask_security.utils import verify_password

from bel_commons.constants import SQLALCHEMY_DATABASE_URI
from bel_commons.core.proxies import celery, manager
from bel_commons.manager_utils import next_or_jsonify
from bel_commons.models import User

__all__ = [
    'receiving_blueprint',
]

log = logging.getLogger(__name__)

receiving_blueprint = Blueprint('receive', __name__, url_prefix='/api/receive')


@receiving_blueprint.route('/', methods=['POST'])
def upload():
    """Receive a JSON serialized BEL graph."""
    user = _get_user()
    if not isinstance(user, User):
        return user

    public = request.headers.get('bel-commons-public') in {'true', 't', 'True', 'yes', 'Y', 'y'}

    # TODO assume https authentication and use this to assign user to receive network function
    payload = request.get_json()
    connection = current_app.config[SQLALCHEMY_DATABASE_URI]
    task = celery.send_task('upload-json', args=[connection, user.id, payload, public])
    return next_or_jsonify('Sent async receive task', task_id=task.id)


def _get_user():
    if request.authorization is None:
        return abort(401, 'Unauthorized')

    username = request.authorization.get('username')
    password = request.authorization.get('password')

    if username is None or password is None:
        return jsonify(success=False, code=1, message='no login information provided')

    user = manager.user_datastore.find_user(email=username)
    if user is None:
        return jsonify(success=False, code=2, message=f'user does not exist: {username}')

    verified = verify_password(password, user.password)
    if not verified:
        return jsonify(success=False, code=3, message=f'bad password for {username}')

    return user
