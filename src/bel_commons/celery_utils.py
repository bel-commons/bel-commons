# -*- coding: utf-8 -*-

"""Utilities for celery."""

from typing import Type

from celery import Celery
from celery.task import Task
from flask import Flask

from bel_commons.models import Report
from pybel import BELGraph, Manager
from pybel.io.line_utils import parse_lines

__all__ = [
    'parse_graph',
    'iterate_report_lines_in_task',
    'register_celery',
]


def parse_graph(report: Report, manager: Manager, task: Task) -> BELGraph:
    """Parse a graph from a report while keeping a celery :class:`Task` informed of progress."""
    lines = iterate_report_lines_in_task(report, task)
    graph = BELGraph()
    parse_lines(
        graph=graph,
        lines=lines,
        manager=manager,
        citation_clearing=report.citation_clearing,
        no_identifier_validation=not report.identifier_validation,
    )
    return graph


def iterate_report_lines_in_task(report: Report, task: Task):
    """Iterate through the lines in a :class:`Report` while keeping a celery :class:`Task` informed of progress."""
    lines = report.get_lines()
    len_lines = len(lines)
    for i, line in enumerate(lines, start=1):
        if not task.request.called_directly:
            task.update_state(state='PROGRESS', meta={
                'task': 'parsing',
                'current_line_number': i,
                'current_line': line,
                'total_lines': len_lines,
            })
        yield line


def register_celery(flask_app: Flask, celery_app: Celery) -> Type[Task]:  # noqa: D202
    """Register the celery app to use the flask app's context."""

    class AppTask(Task):
        """An app-specific celery task."""

        def __call__(self, *args, **kwargs):
            with flask_app.app_context():
                return super().__call__(*args, **kwargs)

    celery_app.Task = AppTask
    celery_app.conf.update(flask_app.config)
    return AppTask
