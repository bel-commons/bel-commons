#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging

from pybel.manager import Manager
from pybel_web.resources.load_networks import alzheimer_directory, upload_bel_directory

log = logging.getLogger(__name__)


def main(connection=None):
    """Load BEL

    :param connection: database connection string to cache, pre-built :class:`Manager`, or None to use default cache
    :type connection: Optional[str or pybel.manager.Manager]
    """
    upload_bel_directory(alzheimer_directory, connection=connection)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
    log.setLevel(logging.INFO)
    main(Manager())
