import importlib
import logging


terminal_tool_module = importlib.import_module("tools.terminal_tool")


def _clear_terminal_env(monkeypatch):
    """Remove terminal env vars that could affect requirements checks."""
    keys = [
        "TERMINAL_ENV",
        "TERMINAL_CONTAINER_CPU",
        "TERMINAL_CONTAINER_DISK",
        "TERMINAL_CONTAINER_MEMORY",
        "TERMINAL_DOCKER_FORWARD_ENV",
        "TERMINAL_DOCKER_VOLUMES",
        "TERMINAL_LIFETIME_SECONDS",
        "TERMINAL_MODAL_MODE",
        "TERMINAL_SSH_HOST",
        "TERMINAL_SSH_PORT",
        "TERMINAL_SSH_USER",
        "TERMINAL_STRICT_BACKEND",
        "TERMINAL_TIMEOUT",
        "MODAL_TOKEN_ID",
        "MODAL_TOKEN_SECRET",
        "HOME",
        "USERPROFILE",
    ]
    for key in keys:
        monkeypatch.delenv(key, raising=False)
    # Default: no Nous subscription — patch both the terminal_tool local
    # binding and tool_backend_helpers (used by resolve_modal_backend_state).
    monkeypatch.setattr(terminal_tool_module, "managed_nous_tools_enabled", lambda: False)
    import tools.tool_backend_helpers as _tbh
    monkeypatch.setattr(_tbh, "managed_nous_tools_enabled", lambda: False)


def test_local_terminal_requirements(monkeypatch, caplog):
    """Local backend uses Hermes' own LocalEnvironment wrapper."""
    _clear_terminal_env(monkeypatch)
    monkeypatch.setenv("TERMINAL_ENV", "local")

    with caplog.at_level(logging.ERROR):
        ok = terminal_tool_module.check_terminal_requirements()

    assert ok is True
    assert "Terminal requirements check failed" not in caplog.text


def test_unknown_terminal_env_logs_error_and_returns_false(monkeypatch, caplog):
    _clear_terminal_env(monkeypatch)
    monkeypatch.setenv("TERMINAL_ENV", "unknown-backend")

    with caplog.at_level(logging.ERROR):
        ok = terminal_tool_module._terminal_backend_ready()

    assert ok is False
    assert any(
        "Unknown TERMINAL_ENV 'unknown-backend'" in record.getMessage()
        for record in caplog.records
    )


def test_ssh_backend_without_host_or_user_logs_and_returns_false(monkeypatch, caplog):
    _clear_terminal_env(monkeypatch)
    monkeypatch.setenv("TERMINAL_ENV", "ssh")

    with caplog.at_level(logging.ERROR):
        ok = terminal_tool_module._terminal_backend_ready()

    assert ok is False
    assert any(
        "SSH backend selected but TERMINAL_SSH_HOST and TERMINAL_SSH_USER" in record.getMessage()
        for record in caplog.records
    )


def test_modal_backend_without_token_or_config_logs_specific_error(monkeypatch, caplog, tmp_path):
    _clear_terminal_env(monkeypatch)
    monkeypatch.setenv("TERMINAL_ENV", "modal")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(terminal_tool_module, "is_managed_tool_gateway_ready", lambda _vendor: False)
    monkeypatch.setattr(terminal_tool_module.importlib.util, "find_spec", lambda _name: object())

    with caplog.at_level(logging.ERROR):
        ok = terminal_tool_module._terminal_backend_ready()

    assert ok is False
    assert any(
        "Modal backend selected but no direct Modal credentials/config was found" in record.getMessage()
        for record in caplog.records
    )


def test_modal_backend_with_managed_gateway_does_not_require_direct_creds_or_minisweagent(monkeypatch, tmp_path):
    _clear_terminal_env(monkeypatch)
    monkeypatch.setattr(terminal_tool_module, "managed_nous_tools_enabled", lambda: True)
    import tools.tool_backend_helpers as _tbh
    monkeypatch.setattr(_tbh, "managed_nous_tools_enabled", lambda: True)
    monkeypatch.setenv("TERMINAL_ENV", "modal")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("TERMINAL_MODAL_MODE", "managed")
    monkeypatch.setattr(terminal_tool_module, "is_managed_tool_gateway_ready", lambda _vendor: True)
    monkeypatch.setattr(
        terminal_tool_module.importlib.util,
        "find_spec",
        lambda _name: (_ for _ in ()).throw(AssertionError("should not be called")),
    )

    assert terminal_tool_module.check_terminal_requirements() is True


def test_modal_backend_auto_mode_prefers_managed_gateway_over_direct_creds(monkeypatch, tmp_path):
    _clear_terminal_env(monkeypatch)
    monkeypatch.setattr(terminal_tool_module, "managed_nous_tools_enabled", lambda: True)
    import tools.tool_backend_helpers as _tbh
    monkeypatch.setattr(_tbh, "managed_nous_tools_enabled", lambda: True)
    monkeypatch.setenv("TERMINAL_ENV", "modal")
    monkeypatch.setenv("MODAL_TOKEN_ID", "tok-id")
    monkeypatch.setenv("MODAL_TOKEN_SECRET", "tok-secret")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(terminal_tool_module, "is_managed_tool_gateway_ready", lambda _vendor: True)
    monkeypatch.setattr(
        terminal_tool_module.importlib.util,
        "find_spec",
        lambda _name: (_ for _ in ()).throw(AssertionError("should not be called")),
    )

    assert terminal_tool_module.check_terminal_requirements() is True


def test_modal_backend_direct_mode_does_not_fall_back_to_managed(monkeypatch, caplog, tmp_path):
    _clear_terminal_env(monkeypatch)
    monkeypatch.setenv("TERMINAL_ENV", "modal")
    monkeypatch.setenv("TERMINAL_MODAL_MODE", "direct")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(terminal_tool_module, "is_managed_tool_gateway_ready", lambda _vendor: True)

    with caplog.at_level(logging.ERROR):
        ok = terminal_tool_module._terminal_backend_ready()

    assert ok is False
    assert any(
        "TERMINAL_MODAL_MODE=direct" in record.getMessage()
        for record in caplog.records
    )


def test_modal_backend_managed_mode_does_not_fall_back_to_direct(monkeypatch, caplog, tmp_path):
    _clear_terminal_env(monkeypatch)
    monkeypatch.setenv("TERMINAL_ENV", "modal")
    monkeypatch.setenv("TERMINAL_MODAL_MODE", "managed")
    monkeypatch.setenv("MODAL_TOKEN_ID", "tok-id")
    monkeypatch.setenv("MODAL_TOKEN_SECRET", "tok-secret")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(terminal_tool_module, "is_managed_tool_gateway_ready", lambda _vendor: False)

    with caplog.at_level(logging.ERROR):
        ok = terminal_tool_module._terminal_backend_ready()

    assert ok is False
    assert any(
        "Nous Tool Gateway access is not currently available" in record.getMessage()
        for record in caplog.records
    )


def test_modal_backend_managed_mode_without_feature_flag_logs_clear_error(monkeypatch, caplog, tmp_path):
    _clear_terminal_env(monkeypatch)
    monkeypatch.setenv("TERMINAL_ENV", "modal")
    monkeypatch.setenv("TERMINAL_MODAL_MODE", "managed")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(terminal_tool_module, "is_managed_tool_gateway_ready", lambda _vendor: False)

    with caplog.at_level(logging.ERROR):
        ok = terminal_tool_module._terminal_backend_ready()

    assert ok is False
    assert any(
        "Nous Tool Gateway access is not currently available" in record.getMessage()
        for record in caplog.records
    )


# --- Auto-fallback contract (never brick the shell) --------------------------
# check_terminal_requirements() keeps the terminal tool AVAILABLE even when the
# configured non-local backend isn't ready, so _create_environment can fall
# back to local at runtime instead of the agent losing its shell entirely.
# terminal.strict_backend=true (TERMINAL_STRICT_BACKEND) restores hard-fail.


def test_broken_backend_keeps_terminal_tool_available_non_strict(monkeypatch, caplog):
    _clear_terminal_env(monkeypatch)
    monkeypatch.setenv("TERMINAL_ENV", "ssh")  # ssh with no host/user => not ready

    with caplog.at_level(logging.WARNING):
        ok = terminal_tool_module.check_terminal_requirements()

    # Probe says not-ready, but the tool stays offered (falls back to local).
    assert terminal_tool_module._terminal_backend_ready() is False
    assert ok is True


def test_broken_backend_disables_terminal_tool_in_strict_mode(monkeypatch):
    _clear_terminal_env(monkeypatch)
    monkeypatch.setenv("TERMINAL_ENV", "ssh")
    monkeypatch.setenv("TERMINAL_STRICT_BACKEND", "1")

    assert terminal_tool_module.check_terminal_requirements() is False


def test_broken_local_backend_still_disables_even_non_strict(monkeypatch):
    # A failing *local* backend is a genuine problem, not something to mask
    # behind fallback — the tool should be disabled.
    _clear_terminal_env(monkeypatch)
    monkeypatch.setenv("TERMINAL_ENV", "local")
    monkeypatch.setattr(terminal_tool_module, "_terminal_backend_ready", lambda: False)

    assert terminal_tool_module.check_terminal_requirements() is False


def test_create_environment_falls_back_to_local_on_backend_failure(monkeypatch):
    _clear_terminal_env(monkeypatch)

    def _boom(**_kwargs):
        raise ImportError("Feature 'terminal.daytona' unavailable: not writable")

    monkeypatch.setattr(terminal_tool_module, "_create_environment_impl", _boom)
    # Drain any prior notice.
    terminal_tool_module.get_backend_fallback_notice()

    env = terminal_tool_module._create_environment(
        env_type="daytona", image="", cwd=".", timeout=30,
    )

    assert isinstance(env, terminal_tool_module._LocalEnvironment)
    notice = terminal_tool_module.get_backend_fallback_notice()
    assert notice is not None and "daytona" in notice
    # Notice is one-shot.
    assert terminal_tool_module.get_backend_fallback_notice() is None


def test_create_environment_reraises_in_strict_mode(monkeypatch):
    _clear_terminal_env(monkeypatch)
    monkeypatch.setenv("TERMINAL_STRICT_BACKEND", "1")

    def _boom(**_kwargs):
        raise ImportError("boom")

    monkeypatch.setattr(terminal_tool_module, "_create_environment_impl", _boom)

    import pytest
    with pytest.raises(ImportError):
        terminal_tool_module._create_environment(
            env_type="daytona", image="", cwd=".", timeout=30,
        )


def test_create_environment_never_masks_local_failure(monkeypatch):
    _clear_terminal_env(monkeypatch)

    def _boom(**_kwargs):
        raise RuntimeError("local is genuinely broken")

    monkeypatch.setattr(terminal_tool_module, "_create_environment_impl", _boom)

    import pytest
    with pytest.raises(RuntimeError):
        terminal_tool_module._create_environment(
            env_type="local", image="", cwd=".", timeout=30,
        )
