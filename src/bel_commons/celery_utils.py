# -*- coding: utf-8 -*-

"""Utilities for celery."""

from celery.task import Task

from bel_commons.models import Report
from pybel import BELGraph, Manager
from pybel.io.line_utils import parse_lines

__all__ = [
    'parse_graph',
]


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


def parse_graph(report: Report, manager: Manager, task: Task) -> BELGraph:
    """Parse a graph from a report while keeping a celery :class:`Task` informed of progress."""
    lines = iterate_report_lines_in_task(report, task)
    graph = BELGraph()
    parse_lines(
        graph=graph,
        lines=lines,
        manager=manager,
        allow_nested=report.allow_nested,
        citation_clearing=report.citation_clearing,
        no_identifier_validation=not report.identifier_validation,
    )
    return graph
