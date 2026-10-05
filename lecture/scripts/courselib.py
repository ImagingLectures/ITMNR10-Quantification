"""
Path helpers for lecture notebooks.

A notebook may be executed in three different working directories:

* interactively in Jupyter          -> cwd is the lecture folder
* during a per-lecture render       -> cwd is the lecture folder
* during the whole-course render    -> cwd is the project root

``lecture_dir()`` resolves the correct lecture folder in all three cases:
``build.py`` injects ``COURSE_LECTURE_DIR`` into the environment, and when it
is absent the folder is found by walking upwards to the nearest
``lecture.yml``.

Use it in notebooks like this::

    from courselib import data_path, figure_path
    df = pd.read_csv(data_path("transmission.csv"))
"""
from __future__ import annotations

import os
from pathlib import Path

__all__ = ["lecture_dir", "lecture_path", "data_path", "figure_path", "project_root"]


def lecture_dir() -> Path:
    """Absolute path of the lecture folder the current notebook belongs to."""
    env = os.environ.get("COURSE_LECTURE_DIR")
    if env:
        return Path(env).resolve()

    here = Path.cwd().resolve()
    for candidate in (here, *here.parents):
        if (candidate / "lecture.yml").exists():
            return candidate
    return here


def project_root() -> Path:
    """Absolute path of the course root (the folder holding ``course.yml``)."""
    here = lecture_dir()
    for candidate in (here, *here.parents):
        if (candidate / "course.yml").exists():
            return candidate
    return here


def lecture_path(*parts: str) -> Path:
    """Path relative to the lecture folder."""
    return lecture_dir().joinpath(*parts)


def data_path(*parts: str) -> Path:
    """Path relative to the lecture's ``data/`` folder."""
    return lecture_dir().joinpath("data", *parts)


def figure_path(*parts: str) -> Path:
    """Path relative to the lecture's ``figures/`` folder."""
    return lecture_dir().joinpath("figures", *parts)
