import pathlib
import re
import subprocess
import sys
from typing import Union

import pytest

from vulture import core

REPO = pathlib.Path(__file__).resolve().parents[1]
WHITELISTS = [
    str(path) for path in (REPO / "vulture" / "whitelists").glob("*.py")
]


def call_vulture(args, **kwargs):
    return subprocess.call(
        [sys.executable, "-m", "vulture"] + args, cwd=REPO, **kwargs
    )


def check(items_or_names, expected_names):
    """items_or_names must be a collection of Items or a set of strings."""
    try:
        assert sorted(item.name for item in items_or_names) == sorted(
            expected_names
        )
    except AttributeError:
        assert items_or_names == set(expected_names)


def check_unreachable(v, lineno, size, name):
    assert len(v.unreachable_code) == 1
    item = v.unreachable_code[0]
    assert item.first_lineno == lineno
    assert item.size == size
    assert item.name == name


def normalize_group_numbers(regex: Union[str, re.Pattern]) -> str:
    """
    This function normalizes group numbers in a regular expression.

    It identifies all group numbers (strings starting with 'g' followed by
    digits, preceded by '?P<'), maps them to new group numbers ('g0', 'g1',
    'g2', etc., in the order they appear), and replaces the old group numbers
    with the new ones in the regex. This is useful for comparing regexes with
    the same structure but different group numbers.

    Note: It assumes group numbers are unique within each regex pattern. If the
    same group number is used for different groups within a single regex
    pattern, this function might not work correctly.
    """
    if isinstance(regex, re.Pattern):
        regex = regex.pattern

    group_numbers = re.findall(r"(?<=\?P<)g\d+", regex)
    group_mapping = {old: f"g{i}" for i, old in enumerate(set(group_numbers))}
    for old, new in group_mapping.items():
        regex = regex.replace(old, new)
    return regex


def normalize_exclude(d: dict) -> dict:
    d["exclude"] = [normalize_group_numbers(regex) for regex in d["exclude"]]
    return d


@pytest.fixture
def v():
    return core.Vulture(verbose=True)
