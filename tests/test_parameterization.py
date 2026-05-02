"""Tests for v0.2 parameterization primitives."""

from __future__ import annotations

import contextvars
import importlib
from dataclasses import FrozenInstanceError
from typing import Any

import pytest


def _public(name: str) -> Any:
    import writesql

    assert hasattr(writesql, name), f"writesql.{name} is not exported"
    return getattr(writesql, name)


def _parameterization_module() -> Any:
    try:
        return importlib.import_module("writesql._parameterization")
    except ModuleNotFoundError:
        pytest.fail("writesql._parameterization is missing")


def _run_isolated(callback: Any) -> Any:
    return contextvars.Context().run(callback)


@pytest.fixture(autouse=True)
def reset_parameterization():
    module = _parameterization_module()
    module._reset_parameterization()
    yield
    module._reset_parameterization()


def test_parameterize_sequence_stores_current_config():
    parameterize = _public("parameterize")
    module = _parameterization_module()

    def configure():
        placeholder = lambda p: "?"

        parameterize("sequence", placeholder=placeholder)
        config = module.current_parameterization()

        assert config.style == "sequence"
        assert config.placeholder is placeholder

    _run_isolated(configure)


def test_parameterization_exports_are_in_public_all():
    import writesql

    assert {
        "parameterize",
        "Param",
        "CompiledSQL",
        "ConfigurationError",
    }.issubset(writesql.__all__)


def test_parameterize_mapping_stores_current_config():
    parameterize = _public("parameterize")
    module = _parameterization_module()

    def configure():
        placeholder = lambda p: f":{p.key}"

        parameterize("mapping", placeholder=placeholder)
        config = module.current_parameterization()

        assert config.style == "mapping"
        assert config.placeholder is placeholder

    _run_isolated(configure)


def test_parameterize_config_is_process_global_across_contexts():
    parameterize = _public("parameterize")
    module = _parameterization_module()
    placeholder = lambda p: "?"

    def configure():
        parameterize("sequence", placeholder=placeholder)

    contextvars.Context().run(configure)

    config = module.current_parameterization()
    assert config is not None
    assert config.style == "sequence"
    assert config.placeholder is placeholder


def test_parameterize_rejects_unknown_style():
    parameterize = _public("parameterize")
    ConfigurationError = _public("ConfigurationError")

    with pytest.raises(ConfigurationError, match="style"):
        parameterize("named", placeholder=lambda p: "?")


def test_parameterize_rejects_non_callable_placeholder():
    parameterize = _public("parameterize")
    ConfigurationError = _public("ConfigurationError")

    with pytest.raises(ConfigurationError, match="placeholder"):
        parameterize("sequence", placeholder="?")


def test_param_is_immutable_and_exposes_metadata_fields():
    Param = _public("Param")

    param = Param(
        name="start_date",
        index=1,
        key="start_date_1",
        value="2024-01-01",
    )

    assert param.name == "start_date"
    assert param.index == 1
    assert param.key == "start_date_1"
    assert param.value == "2024-01-01"
    with pytest.raises(FrozenInstanceError):
        param.index = 2


def test_build_param_generates_key_from_name_and_index():
    Param = _public("Param")
    module = _parameterization_module()

    assert module.build_param("start_date", 1, "2024-01-01") == Param(
        name="start_date",
        index=1,
        key="start_date_1",
        value="2024-01-01",
    )


def test_placeholder_helper_passes_generated_param_metadata():
    parameterize = _public("parameterize")
    Param = _public("Param")
    module = _parameterization_module()

    def configure():
        seen = []

        def placeholder(param):
            seen.append(param)
            return f":{param.key}"

        parameterize("mapping", placeholder=placeholder)

        assert (
            module.render_placeholder("start_date", 1, "2024-01-01")
            == ":start_date_1"
        )
        assert seen == [
            Param(
                name="start_date",
                index=1,
                key="start_date_1",
                value="2024-01-01",
            )
        ]

    _run_isolated(configure)


def test_placeholder_helper_rejects_non_string_return_value():
    parameterize = _public("parameterize")
    ConfigurationError = _public("ConfigurationError")
    module = _parameterization_module()

    def configure():
        parameterize("sequence", placeholder=lambda p: 123)

        with pytest.raises(ConfigurationError, match="str"):
            module.render_placeholder("start_date", 1, "2024-01-01")

    _run_isolated(configure)


def test_compiled_sql_is_a_string_with_params_and_debug_sql():
    module = _parameterization_module()

    sql = module.CompiledSQL(
        "SELECT * FROM orders WHERE created_at >= ?",
        params=["2024-01-01"],
        debug_sql="SELECT * FROM orders WHERE created_at >= '2024-01-01'",
    )

    assert isinstance(sql, str)
    assert issubclass(module.CompiledSQL, str)
    assert str(sql) == "SELECT * FROM orders WHERE created_at >= ?"
    assert sql.params == ["2024-01-01"]
    assert sql.debug_sql == "SELECT * FROM orders WHERE created_at >= '2024-01-01'"
