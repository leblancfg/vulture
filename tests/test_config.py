"""
Unit tests for config file and CLI argument parsing.
"""

from io import BytesIO
from textwrap import dedent
from unittest.mock import patch

import pytest

from vulture.config import (
    DEFAULTS,
    _check_input_config,
    _parse_args,
    _parse_toml,
    find_gitignore,
    make_config,
    InputError,
)
from vulture.utils import fnmatch_to_regex
from . import normalize_exclude


def get_toml_bytes(toml_str: str) -> BytesIO:
    """
    Wrap a string in BytesIO to play the role of the incoming config stream.
    """
    return BytesIO(bytes(toml_str, "utf-8"))


def test_cli_args():
    """
    Ensure that CLI arguments are converted to a config object.
    """
    expected = dict(
        paths=["path1", "path2"],
        exclude=["file*.py", "dir/"],
        ignore_decorators=["deco1", "deco2"],
        ignore_names=["name1", "name2"],
        make_whitelist=True,
        min_confidence=10,
        sort_by_size=True,
        verbose=True,
    )
    result = _parse_args(
        [
            "--exclude=file*.py,dir/",
            "--ignore-decorators=deco1,deco2",
            "--ignore-names=name1,name2",
            "--make-whitelist",
            "--min-confidence=10",
            "--sort-by-size",
            "--verbose",
            "path1",
            "path2",
        ]
    )
    assert isinstance(result, dict)
    assert result == expected


def test_toml_config():
    """
    Ensure parsing of TOML files results in a valid config object.
    """
    expected = dict(
        paths=["path1", "path2"],
        exclude=["file*.py", "dir/"],
        ignore_decorators=["deco1", "deco2"],
        ignore_names=["name1", "name2"],
        make_whitelist=True,
        min_confidence=10,
        sort_by_size=True,
        verbose=True,
    )
    data = get_toml_bytes(
        dedent(
            """\
        [tool.vulture]
        exclude = ["file*.py", "dir/"]
        ignore_decorators = ["deco1", "deco2"]
        ignore_names = ["name1", "name2"]
        make_whitelist = true
        min_confidence = 10
        sort_by_size = true
        verbose = true
        paths = ["path1", "path2"]
        """
        )
    )
    result = _parse_toml(data)
    assert isinstance(result, dict)
    assert result == expected


def test_toml_config_with_heterogenous_array():
    """
    Ensure parsing of TOML files results in a valid config object, even if some
    other part of the file contains an array of mixed types.
    """
    expected = dict(
        paths=["path1", "path2"],
        exclude=["file*.py", "dir/"],
        ignore_decorators=["deco1", "deco2"],
        ignore_names=["name1", "name2"],
        make_whitelist=True,
        min_confidence=10,
        sort_by_size=True,
        verbose=True,
    )
    data = get_toml_bytes(
        dedent(
            """\
        [tool.foo]
        # comment for good measure
        problem_array = [{a = 1}, [2,3,4], "foo"]

        [tool.vulture]
        exclude = ["file*.py", "dir/"]
        ignore_decorators = ["deco1", "deco2"]
        ignore_names = ["name1", "name2"]
        make_whitelist = true
        min_confidence = 10
        sort_by_size = true
        verbose = true
        paths = ["path1", "path2"]
        """
        )
    )
    result = _parse_toml(data)
    assert isinstance(result, dict)
    assert result == expected


def test_config_merging():
    """
    If we have both CLI args and a ``pyproject.toml`` file, the CLI args should
    have precedence.
    """
    toml = get_toml_bytes(
        dedent(
            """\
        [tool.vulture]
        exclude = ["toml_exclude"]
        ignore_decorators = ["toml_deco"]
        ignore_names = ["toml_name"]
        make_whitelist = false
        min_confidence = 10
        sort_by_size = false
        verbose = false
        paths = ["toml_path"]
        """
        )
    )
    cliargs = [
        "--exclude=cli_exclude",
        "--ignore-decorators=cli_deco",
        "--ignore-names=cli_name",
        "--make-whitelist",
        "--min-confidence=20",
        "--sort-by-size",
        "--verbose",
        "cli_path",
    ]
    result = make_config(cliargs, toml)
    expected = dict(
        paths=["cli_path"],
        # Specifically for this repo, passing an `exclude` argument means
        # we don't use this repo's .gitignore but only the `exclude` patterns.
        exclude=[fnmatch_to_regex("cli_exclude")],  # regex syntax, not fnmatch
        ignore_decorators=["cli_deco"],
        ignore_names=["cli_name"],
        make_whitelist=True,
        min_confidence=20,
        sort_by_size=True,
        verbose=True,
    )
    # This test was flaking because the auto-generated capture group numbers in
    # the `exclude` regexes sometime differ.
    # Normalizing them with auto-incremented ones makes the test deterministic.
    assert normalize_exclude(result) == normalize_exclude(expected)


@patch("vulture.config._parse_gitignore_excludes", return_value=["asdf"])
@patch("vulture.config._parse_toml", return_value={})
def test_use_gitignore_if_no_exclude(_, __):
    """
    Ensure that the gitignore patterns are used if no exclude is passed.
    """
    expected_exclude = ["asdf"]
    result = make_config(["path1"])["exclude"]
    assert isinstance(result, list)
    assert result == expected_exclude


def test_config_merging_missing():
    """
    If we have set a boolean value in the TOML file, but not on the CLI, we
    want the TOML value to be taken.
    """
    toml = get_toml_bytes(
        dedent(
            """\
        [tool.vulture]
        verbose = true
        ignore_names = ["name1"]
        """
        )
    )
    cliargs = [
        "cli_path",
    ]
    result = make_config(cliargs, toml)
    assert result["verbose"] is True
    assert result["ignore_names"] == ["name1"]


def test_config_merging_toml_paths_only():
    """
    If we have paths in the TOML but not on the CLI, the TOML paths should be
    used.
    """
    toml = get_toml_bytes(
        dedent(
            """\
        [tool.vulture]
        paths = ["path1", "path2"]
        """
        )
    )
    cliargs = [
        "--exclude=test_*.py",
    ]
    result = make_config(cliargs, toml)
    assert result["paths"] == ["path1", "path2"]
    assert result["exclude"] == [fnmatch_to_regex("test_*.py")]


def test_invalid_config_options_output():
    """
    If the config file contains unknown options we want to abort.
    """

    with pytest.raises(InputError):
        _check_input_config({"unknown_key_1": 1})


@pytest.mark.parametrize("key, value", list(DEFAULTS.items()))
def test_incompatible_option_type(key, value):
    """
    If a config value has a different type from the default value we abort.
    """
    wrong_types = {int, str, list, bool} - {type(value)}
    for wrong_type in wrong_types:
        test_value = wrong_type()
        with pytest.raises(InputError):
            _check_input_config({key: test_value})


def test_missing_paths():
    """
    If the script is run without any paths, we want to abort.
    """
    with pytest.raises(InputError):
        make_config([])


@pytest.fixture
def gitignore_paths(tmp_path):
    """
    root  # Project root
    ├── .gitignore
    ├── test
    └── src  # Git submodule
        ├── .gitignore
        └── foo.py
    """

    def resolve_gitignore(path):
        gitignore = (path / ".gitignore").resolve()
        gitignore.touch()
        return gitignore

    root = tmp_path
    root_gitignore = resolve_gitignore(root)

    test_dir = root / "test"
    test_dir.mkdir()

    src_dir = root / "src"
    src_dir.mkdir()

    # Imagine a git submodule with a .gitignore file
    src_gitignore = resolve_gitignore(src_dir)
    src_python = src_dir / "foo.py"
    src_python.touch()
    yield root, root_gitignore, test_dir, src_dir, src_gitignore, src_python


def test_find_gitignore_root_no_paths(gitignore_paths, monkeypatch):
    root, root_gitignore, *_ = gitignore_paths
    monkeypatch.chdir(root)
    assert find_gitignore() == root_gitignore  # No paths


def test_find_gitignore_root_path_from_list(gitignore_paths):
    root, root_gitignore, *_ = gitignore_paths
    assert find_gitignore([root]) == root_gitignore  # list[Path]
    assert find_gitignore([str(root)]) == root_gitignore  # list[str]


def test_find_gitignore_from_str_and_path(gitignore_paths):
    root, root_gitignore, *_ = gitignore_paths
    assert find_gitignore(root) == root_gitignore  # pathlib.Path
    assert find_gitignore(str(root)) == root_gitignore  # str


def test_find_gitignore_common_parent(gitignore_paths):
    root_gitignore, test_dir, src_dir, *_ = gitignore_paths[1:]
    # Test that we find the root gitignore as the common parent
    assert find_gitignore([src_dir, test_dir]) == root_gitignore


def test_find_gitignore_in_a_different_repo_root(gitignore_paths):
    src_dir, src_gitignore, src_python, *_ = gitignore_paths[3:]
    # If we only run in the submodule, we should find the submodule gitignore
    assert find_gitignore([src_dir]) == src_gitignore
    # Same applies for a specific file in the submodule
    assert find_gitignore([src_python]) == src_gitignore


def test_find_gitignore_relative_path(gitignore_paths, monkeypatch):
    test_dir, _, src_gitignore, __ = gitignore_paths[2:]
    # Even if we're outside the submodule, we should still find the submodule
    # if that's the only path we're given
    monkeypatch.chdir(test_dir)
    assert find_gitignore("../src/a.py") == src_gitignore
