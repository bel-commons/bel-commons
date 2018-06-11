# -*- coding: utf-8 -*-

"""Utilities for the analytical service."""

import logging
from collections import defaultdict

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

__all__ = [
    'get_dataframe_from_experiments',
]

log = logging.getLogger(__name__)


def get_dataframe_from_experiments(experiments, *, normalize=None, clusters=None, seed=None):
    """Build a Pandas DataFrame from the list of experiments.

    :param iter[Experiment] experiments: Experiments to work on
    :param bool normalize:
    :param Optional[int] clusters: Number of clusters to use in k-means
    :param Optional[int] seed: Random number seed
    :rtype: pandas.DataFrame
    """
    x_label = ['Type', 'Namespace', 'Name']

    entries = defaultdict(list)

    for experiment in experiments:
        if experiment.result is None:
            continue

        x_label.append('[{}] {}'.format(experiment.id, experiment.source_name))

        for (func, namespace, name), values in sorted(experiment.get_data_list()):
            median_value = values[3]
            entries[func, namespace, name].append(median_value)

    result = [
        list(entry) + list(values)
        for entry, values in entries.items()
    ]

    df = pd.DataFrame(result, columns=x_label)
    df = df.fillna(0).round(4)

    data_columns = x_label[3:]

    if normalize:
        df[data_columns] = df[data_columns].apply(lambda x: (x - np.min(x)) / (np.max(x) - np.min(x)))

    if clusters is not None:
        log.info('using %d-means clustering', clusters)
        log.info('using seed: %s', seed)
        km = KMeans(n_clusters=clusters, random_state=seed)
        km.fit(df[data_columns])
        df['Group'] = km.labels_ + 1
        df = df.sort_values('Group')

    return df
