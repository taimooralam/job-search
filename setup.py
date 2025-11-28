"""
Setup script for job-search project.

Allows development installation with `pip install -e .`
"""

from setuptools import setup, find_packages

setup(
    name="job-search",
    version="0.1.0",
    packages=find_packages(),
    python_requires=">=3.11",
)
