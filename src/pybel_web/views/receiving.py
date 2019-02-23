# -*- coding: utf-8 -*-

"""A blueprint for receiving uploads of graphs as JSON."""

import logging

from flask import Blueprint, abort, current_app, jsonify, request
from flask_security.utils import verify_password

from pybel_web.manager_utils import next_or_jsonify
from pybel_web.models import User
from pybel_web.proxies import celery, manager

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
    connection = current_app.config['SQLALCHEMY_DATABASE_URI']
    task = celery.send_task('upload-json', args=[connection, user.id, payload, public])
    return next_or_jsonify('Sent async receive task', task_id=task.id)


@receiving_blueprint.route('/get_latest_network_version', methods=['POST'])
def get_latest_network_version():
    """Get a network by name.

    ---
    tags:
        - network
    parameters:
      - name: name
        in: query
        description: The network name
        required: true
        type: string
    """
    user = _get_user()
    if not isinstance(user, User):
        return user

    name = request.args.get('name')
    if name is None:
        return jsonify(success=False, code=4, message='name argument not supplied')

    network = manager.get_most_recent_network_by_name(name)

    if network is None:
        return jsonify(success=False, code=5, message='network does not exist')

    if not manager._network_has_permission(user=user, network_id=network.id):
        return jsonify(success=False, code=6, message='user does not have rights to network')

    return jsonify(success=True, code=0, network=network.to_json())


def _get_user():
    if request.authorization is None:
        return abort(401, 'Unauthorized')

    username = request.authorization.get('username')
    password = request.authorization.get('password')

    if username is None or password is None:
        return jsonify(success=False, code=1, message='no login information provided')

    user = manager.user_datastore.find_user(email=username)
    if user is None:
        return jsonify(success=False, code=2, message='user does not exist')

    verified = verify_password(password, user.password)
    if not verified:
        return jsonify(success=False, code=3, message='bad password')

    return user
