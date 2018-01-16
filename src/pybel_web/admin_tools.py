# -*- coding: utf-8 -*-

"""This module has some nice admin only tools"""

import logging

from flask import Blueprint, current_app, render_template
from flask_security import roles_required

from .utils import manager, next_or_jsonify

log = logging.getLogger(__name__)

admin_tools_blueprint = Blueprint('admintools', __name__)


