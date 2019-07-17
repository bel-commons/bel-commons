# -*- coding: utf-8 -*-

"""Routing converters."""

from werkzeug.routing import BaseConverter

__all__ = [
    'ListConverter',
    'IntListConverter',
]


class ListConverter(BaseConverter):
    """A converter for comma-delimited lists."""

    #: The separator for lists
    sep = ','

    def to_python(self, value: str):
        """Convert a delimited list."""
        return value.split(self.sep)

    def to_url(self, values):
        """Output a list joined with a delimiter."""
        return self.sep.join(BaseConverter.to_url(self, value) for value in values)


class IntListConverter(ListConverter):
    """A converter for comma-delimited integer lists."""

    def to_python(self, value: str):
        """Convert a delimited list of integers."""
        return [int(entry) for entry in super().to_python(value)]
