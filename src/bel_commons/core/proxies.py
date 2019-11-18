# -*- coding: utf-8 -*-

"""Local proxies for BEL Commons."""

from .flask_bio2bel import FlaskBio2BEL

__all__ = [
    'flask_bio2bel',
]

flask_bio2bel = FlaskBio2BEL.get_proxy()
