"""hermes-fork: coverage for managed_uv.ensure_uv_cache_env.

Extracted from tests/hermes_cli/test_uv_tool_update.py when upstream removed
pip/uv-tool update support (upstream #68217 rip-out) and deleted that test
file. ensure_uv_cache_env is a fork-owned guard that survives: it pins a
stale/foreign UV_CACHE_DIR (e.g. a /state/.env written before a HERMES_HOME
migration moved the home from /home/hermeswebui to /home/hermes) to a writable
$HERMES_HOME/cache/uv, and is still called from update_managed_uv() during
`hermes update`. Regression for the support report:
  error: Failed to initialize cache at `/home/hermeswebui/.hermes/cache/uv`
    Caused by: failed to create directory ...: Permission denied (os error 13)
"""

import os


class TestEnsureUvCacheEnv:
    def test_pins_cache_under_hermes_home_when_unset(self, tmp_path, monkeypatch):
        from hermes_cli import managed_uv

        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        monkeypatch.delenv("UV_CACHE_DIR", raising=False)

        result = managed_uv.ensure_uv_cache_env()

        assert result == str(tmp_path / "cache" / "uv")
        assert os.environ["UV_CACHE_DIR"] == str(tmp_path / "cache" / "uv")
        assert (tmp_path / "cache" / "uv").is_dir()

    def test_overrides_unwritable_inherited_cache(self, tmp_path, monkeypatch):
        """A UV_CACHE_DIR pointing at an uncreatable path (the foreign-home case)
        is replaced with the managed $HERMES_HOME/cache/uv path."""
        from hermes_cli import managed_uv

        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        # A regular file blocks creating a dir beneath it -> NotADirectoryError,
        # standing in for "owned by another user / Permission denied".
        blocker = tmp_path / "blocker"
        blocker.write_text("x")
        monkeypatch.setenv("UV_CACHE_DIR", str(blocker / "uv"))

        managed_uv.ensure_uv_cache_env()

        assert os.environ["UV_CACHE_DIR"] == str(tmp_path / "cache" / "uv")

    def test_keeps_writable_inherited_cache(self, tmp_path, monkeypatch):
        """A user-set, writable UV_CACHE_DIR is honored, not clobbered."""
        from hermes_cli import managed_uv

        monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
        custom = tmp_path / "custom-cache"
        monkeypatch.setenv("UV_CACHE_DIR", str(custom))

        result = managed_uv.ensure_uv_cache_env()

        assert result == str(custom)
        assert os.environ["UV_CACHE_DIR"] == str(custom)
