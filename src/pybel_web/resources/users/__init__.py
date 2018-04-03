# -*- coding: utf-8 -*-

"""Stores default user information"""

import logging
import os

log = logging.getLogger(__name__)

dir_path = os.path.dirname(os.path.realpath(__file__))
default_users_path = os.path.join(dir_path, 'default_users.json')
exists_default_users_path = os.path.exists(default_users_path)
