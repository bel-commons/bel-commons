#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Load alzheimer's BEL."""

import logging
from typing import Optional

from bel_commons.resources.load_networks import alzheimer_directory, upload_bel_directory
from pybel.manager import Manager

log = logging.getLogger(__name__)


def main(manager: Optional[Manager] = None):
    """Load BEL."""
    if manager is None:
        manager = Manager()

    upload_bel_directory(alzheimer_directory, manager)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
    log.setLevel(logging.INFO)
    main(Manager())
