#!/usr/bin/env bash

# This script loads all of the sample resources for BEL Commons.
# Assumes: the environment variable BMS_BASE is set.

python3 load_omics.py
python3 load_networks.py
python3 load_experiments.py
