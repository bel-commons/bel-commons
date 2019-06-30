# -*- coding: utf-8 -*-

"""Various endpoints for BEL Commons."""

from .curation import curation_blueprint  # noqa: F401
from .experiment_service import experiment_blueprint  # noqa: F401
from .help import help_blueprint  # noqa: F401
from .parser_endpoint import build_parser_service  # noqa: F401
from .receiving import receiving_blueprint  # noqa: F401
from .reporting import reporting_blueprint  # noqa: F401
from .uploading import uploading_blueprint  # noqa: F401
