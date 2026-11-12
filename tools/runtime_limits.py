"""Keep the chat wrapper outside the bounded model turn and its cleanup window."""
MAX_MODEL_TURN_SECONDS = 600
HARNESS_TIMEOUT_SECONDS = 900
HARNESS_CLEANUP_SECONDS = 120


def require_harness_budget(config):
    outer = config.get('harness_timeout_seconds')
    if outer is None:
        return  # Local operator/job calls have no wn-codex wrapper.
    try:
        seconds = int(outer)
    except (TypeError, ValueError):
        raise ValueError('Invalid harness timeout configuration') from None
    turn = config['turn_timeout_seconds']
    if not 30 <= turn <= MAX_MODEL_TURN_SECONDS:
        raise ValueError('Invalid bounded model turn timeout')
    if seconds < turn + HARNESS_CLEANUP_SECONDS:
        raise ValueError('Harness timeout configuration must cover the model turn and cleanup before starting work')
