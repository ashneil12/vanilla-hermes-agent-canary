from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
STAGE2_HOOK = REPO_ROOT / "docker" / "stage2-hook.sh"


def test_bind_mounted_config_chown_happens_before_non_root_bootstrap():
    """Keep bind-mounted config repair in the root-only s6 cont-init phase.

    Upstream moved the real bootstrap from docker/entrypoint.sh to the s6
    stage2 hook. The security invariant remains the same: config.yaml ownership
    must be repaired before any hermes-user bootstrap work starts.
    """
    text = STAGE2_HOOK.read_text(encoding="utf-8")

    root_phase, non_root_phase = text.split("# --- Seed directory structure as hermes user ---", maxsplit=1)

    assert '"$HERMES_HOME/config.yaml"' in root_phase
    assert 'chown hermes:hermes "$HERMES_HOME/config.yaml"' in root_phase
    assert 'chown hermes:hermes "$HERMES_HOME/config.yaml"' not in non_root_phase
