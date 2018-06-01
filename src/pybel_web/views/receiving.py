# -*- coding: utf-8 -*-

import logging

from flask import Blueprint, current_app, jsonify, request
from flask_security.utils import verify_password

from ..manager_utils import next_or_jsonify
from ..models import User
from ..proxies import manager

__all__ = [
    'receiving_blueprint',
]

log = logging.getLogger(__name__)

receiving_blueprint = Blueprint('receive', __name__, url_prefix='/api/receive')


def _get_user():
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


@receiving_blueprint.route('/', methods=['POST'])
def receive():
    """Receive a JSON serialized BEL graph"""
    user = _get_user()
    if not isinstance(user, User):
        return user

    # TODO assume https authentication and use this to assign user to receive network function
    payload = request.get_json()
    connection = current_app.config['SQLALCHEMY_DATABASE_URI']
    task = current_app.celery.send_task('upload-json', args=[connection, user.id, payload])
    return next_or_jsonify('Sent async receive task', task_id=task.id)


def _user_has_rights(user, network):
    pass


@receiving_blueprint.route('/get_latest_network_version', methods=['POST'])
def get_latest_network_version(name):
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

    # check if user has rights to this network first

    if not _user_has_rights(user, network):
        return jsonify(success=False, code=6, message='user does not have rights to network')

    return jsonify(success=True, code=0, network=network.to_json())
