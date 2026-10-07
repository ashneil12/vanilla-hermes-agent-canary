"""hermes-fork: install-dir-home-guard (hermes_fork_home.py wired from hermes_constants / env_loader).

A Hermes home resolving into the read-only /opt/hermes tree (HERMES_HOME lost / HOME=/opt/hermes)
redirects to a writable, agent-shared data home: probed for is-dir + writable, NOT a hardcoded
/opt/data (owned by uid 10000, unwritable from the uid-1024 dashboard container). A stale
persisted .env must never clobber the live HERMES_HOME / HOME.
"""

import os
from pathlib import Path

import hermes_constants
import hermes_fork_home
from hermes_constants import get_default_hermes_root, get_hermes_home
from hermes_cli.env_loader import load_hermes_dotenv


def _wire_install_tree(tmp_path, monkeypatch, *, candidate_exists=True):
    install_dir = tmp_path / "opt" / "hermes"
    data_home = tmp_path / "home" / "hermes" / ".hermes"
    install_dir.mkdir(parents=True)
    if candidate_exists:
        data_home.mkdir(parents=True)
    monkeypatch.setattr(hermes_fork_home, "_DOCKER_INSTALL_DIR", install_dir)
    monkeypatch.setattr(hermes_fork_home, "_DOCKER_DATA_HOME_CANDIDATES", (data_home,))
    monkeypatch.setattr(hermes_fork_home, "_install_dir_home_warned", False)
    monkeypatch.delenv("HERMES_WRITE_SAFE_ROOT", raising=False)
    return install_dir, data_home


# --- seam wiring ---------------------------------------------------------------------------

def test_resolvers_are_wrapped_and_env_loader_is_pinned():
    for name in hermes_fork_home._GUARDED_RESOLVERS:
        assert getattr(getattr(hermes_constants, name), "__hermes_fork_guarded__", False), name
    from hermes_cli import env_loader

    assert getattr(env_loader.load_hermes_dotenv, "__hermes_fork_guarded__", False)


def test_install_is_idempotent():
    before = hermes_constants.get_hermes_home
    hermes_fork_home.install(vars(hermes_constants))
    assert hermes_constants.get_hermes_home is before


# --- resolver guard ------------------------------------------------------------------------

def test_fallback_into_install_tree_redirects(tmp_path, monkeypatch):
    install_dir, data_home = _wire_install_tree(tmp_path, monkeypatch)
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: install_dir)
    monkeypatch.setattr(hermes_constants, "_profile_fallback_warned", True, raising=False)
    assert get_hermes_home() == data_home


def test_explicit_hermes_home_in_install_tree_redirects(tmp_path, monkeypatch):
    install_dir, data_home = _wire_install_tree(tmp_path, monkeypatch)
    monkeypatch.setenv("HERMES_HOME", str(install_dir / ".hermes"))
    assert get_hermes_home() == data_home


def test_no_redirect_when_no_writable_candidate(tmp_path, monkeypatch):
    install_dir, _ = _wire_install_tree(tmp_path, monkeypatch, candidate_exists=False)
    bad = install_dir / ".hermes"
    monkeypatch.setenv("HERMES_HOME", str(bad))
    assert get_hermes_home() == bad  # the failure stays visible


def test_normal_home_untouched(tmp_path, monkeypatch):
    _wire_install_tree(tmp_path, monkeypatch)
    good = tmp_path / "elsewhere" / ".hermes"
    good.mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(good))
    assert get_hermes_home() == good


def test_first_existing_candidate_wins(tmp_path, monkeypatch):
    install_dir = tmp_path / "opt" / "hermes"
    install_dir.mkdir(parents=True)
    missing = tmp_path / "first" / "missing"
    present = tmp_path / "second" / ".hermes"
    present.mkdir(parents=True)
    monkeypatch.setattr(hermes_fork_home, "_DOCKER_INSTALL_DIR", install_dir)
    monkeypatch.setattr(hermes_fork_home, "_DOCKER_DATA_HOME_CANDIDATES", (missing, present))
    monkeypatch.setattr(hermes_fork_home, "_install_dir_home_warned", False)
    monkeypatch.delenv("HERMES_WRITE_SAFE_ROOT", raising=False)
    monkeypatch.setenv("HERMES_HOME", str(install_dir / ".hermes"))
    assert get_hermes_home() == present


def test_write_safe_root_env_takes_precedence(tmp_path, monkeypatch):
    install_dir, _ = _wire_install_tree(tmp_path, monkeypatch)
    forced = tmp_path / "forced" / ".hermes"
    forced.mkdir(parents=True)
    monkeypatch.setenv("HERMES_WRITE_SAFE_ROOT", str(forced))
    monkeypatch.setenv("HERMES_HOME", str(install_dir / ".hermes"))
    assert get_hermes_home() == forced


def test_override_branch_also_guarded(tmp_path, monkeypatch):
    install_dir, data_home = _wire_install_tree(tmp_path, monkeypatch)
    token = hermes_constants.set_hermes_home_override(str(install_dir / ".hermes"))
    try:
        assert get_hermes_home() == data_home
    finally:
        hermes_constants.reset_hermes_home_override(token)


def test_default_root_unset_home_redirects(tmp_path, monkeypatch):
    """get_default_hermes_root() applies the SAME guard (an env-stripped child with HOME=/opt/hermes
    used to hand back /opt/hermes/.hermes and EACCES the webchat document-attach on webfree boxes)."""
    install_dir, data_home = _wire_install_tree(tmp_path, monkeypatch)
    monkeypatch.delenv("HERMES_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: install_dir)
    assert get_default_hermes_root() == data_home
    monkeypatch.setattr(hermes_constants, "_profile_fallback_warned", True, raising=False)
    assert get_default_hermes_root() == get_hermes_home()


def test_default_root_explicit_home_in_install_tree_redirects(tmp_path, monkeypatch):
    install_dir, data_home = _wire_install_tree(tmp_path, monkeypatch)
    monkeypatch.setenv("HERMES_HOME", str(install_dir / ".hermes"))
    assert get_default_hermes_root() == data_home


# --- .env pin ------------------------------------------------------------------------------

def test_persisted_env_cannot_clobber_live_hermes_home_and_home(tmp_path, monkeypatch):
    """The webfree-split upload bug: the official-dashboard process loaded its .env with
    override=True, the .env repointed HERMES_HOME into /opt/hermes, and every write EACCESed."""
    home = tmp_path / "home" / "hermes" / ".hermes"
    home.mkdir(parents=True)
    real_home = tmp_path / "home" / "hermes"
    (home / ".env").write_text(
        "HERMES_HOME=/opt/hermes/.hermes\nHOME=/opt/hermes\nOPENAI_API_KEY=from-dotenv\n", encoding="utf-8"
    )
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("HOME", str(real_home))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    load_hermes_dotenv(hermes_home=home)

    assert os.getenv("HERMES_HOME") == str(home)
    assert os.getenv("HOME") == str(real_home)
    assert os.getenv("OPENAI_API_KEY") == "from-dotenv"  # non-infra keys still load


def test_unset_infra_key_still_loads_from_env(tmp_path, monkeypatch):
    """Only already-set live values are pinned; an unset HERMES_HOME still loads from the file."""
    home = tmp_path / "hermes"
    home.mkdir()
    target = tmp_path / "data"
    target.mkdir()
    (home / ".env").write_text(f"HERMES_HOME={target}\n", encoding="utf-8")
    monkeypatch.delenv("HERMES_HOME", raising=False)

    load_hermes_dotenv(hermes_home=home)

    assert os.getenv("HERMES_HOME") == str(target)
