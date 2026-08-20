'''Kill switch management — two-layer safety system.

L1: Environment variable BOT_ENABLED (GitHub Secret) — instant, no commit needed.
L2: kill_switch.json in repo — visible on dashboard, records reason.

Engine checks L1 first, then L2. If either is OFF, trading is skipped.
'''

import json
import logging
import os
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


DEFAULT_KILL_SWITCH = {
    'enabled': True,
    'reason': '',
    'activated_at': None,
    'activated_by': 'system',
}

# Reject reasons containing HTML/JS metacharacters at write-time (S-02).
# Combined with S-01 webhook validation + S-02 dashboard escaping = triple defense.
_REASON_FORBIDDEN_RE = re.compile(r'[<>&"\'/]')
_REASON_MAX_LEN = 200


def _validate_reason(reason) -> str:
    """Validate kill-switch reason. Raises ValueError on invalid input.

    S-02: defense in depth — reject any HTML/JS metacharacters at write-time so a
    compromised webhook (S-01) or a rogue operator cannot inject persistent XSS
    payloads into the dashboard via kill_switch.json.
    """
    if reason is None or reason == '':
        return ''
    if not isinstance(reason, str):
        raise ValueError(f'reason must be a string, got {type(reason).__name__}')
    if len(reason) > _REASON_MAX_LEN:
        raise ValueError(f'reason too long ({len(reason)} > {_REASON_MAX_LEN} chars)')
    if _REASON_FORBIDDEN_RE.search(reason):
        raise ValueError('reason contains forbidden characters (<>&"\'/)')
    return reason


def load_kill_switch(path: str = 'kill_switch.json') -> dict:
    """Load kill switch state from JSON file.

    S-08: fail-safe on malformed JSON — if the file is corrupt, unreadable, or
    contains a non-dict value, return DEFAULT_KILL_SWITCH (enabled=True) so the
    bot continues trading. The operator can intervene manually via L1 (BOT_ENABLED
    env var) or by re-pushing a valid kill_switch.json. We do NOT fail-closed
    here because L1 is the master switch — L2 corrupting should not halt trading.
    """
    try:
        with open(path, 'r') as f:
            saved = json.load(f)
    except FileNotFoundError:
        return dict(DEFAULT_KILL_SWITCH)
    except PermissionError as e:
        logger.warning('kill_switch.json unreadable (permission denied: %s); '
                       'returning DEFAULT_KILL_SWITCH (enabled=True)', e)
        return dict(DEFAULT_KILL_SWITCH)
    except json.JSONDecodeError as e:
        logger.warning('kill_switch.json is corrupted (JSON parse error: %s); '
                       'returning DEFAULT_KILL_SWITCH (enabled=True) — bot '
                       'continues trading, operator should intervene manually', e)
        return dict(DEFAULT_KILL_SWITCH)
    except OSError as e:
        logger.warning('kill_switch.json could not be read (OS error: %s); '
                       'returning DEFAULT_KILL_SWITCH (enabled=True)', e)
        return dict(DEFAULT_KILL_SWITCH)

    # S-08: defend against valid JSON that isn't a dict (e.g. `[1,2,3]` or `"x"`)
    if not isinstance(saved, dict):
        logger.warning('kill_switch.json contains non-object JSON (%r); '
                       'returning DEFAULT_KILL_SWITCH (enabled=True)',
                       type(saved).__name__)
        return dict(DEFAULT_KILL_SWITCH)

    return {**DEFAULT_KILL_SWITCH, **saved}


def save_kill_switch(ks: dict, path: str = 'kill_switch.json'):
    """Save kill switch state atomically."""
    import tempfile
    dir_name = os.path.dirname(path) or '.'
    os.makedirs(dir_name, exist_ok=True)
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
        with os.fdopen(fd, 'w') as f:
            json.dump(ks, f, indent=2, default=str)
        os.replace(tmp_path, path)
        tmp_path = None  # successfully replaced, no cleanup needed
    except Exception:
        if tmp_path is not None and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def check_kill_switch(ks_path: str = 'kill_switch.json') -> tuple:
    """Check both kill switch layers. Returns (is_alive, reason).

    Returns:
        (True, '') — bot should run
        (False, reason) — bot is killed, reason explains why
    """
    # L1: Environment variable (GitHub Secret)
    l1_enabled = os.environ.get('BOT_ENABLED', 'true').lower() == 'true'
    if not l1_enabled:
        return False, 'L1: BOT_ENABLED env var is false'

    # L2: kill_switch.json
    ks = load_kill_switch(ks_path)
    if not ks['enabled']:
        reason = ks.get('reason', 'No reason specified')
        return False, f'L2: {reason}'

    return True, ''


def activate_kill_switch(reason: str, ks_path: str = 'kill_switch.json',
                        activated_by: str = 'manual'):
    """Activate kill switch (disable bot).

    S-02: validates `reason` before writing — rejects HTML/JS metacharacters
    so persistent XSS cannot be injected via kill_switch.json.
    """
    reason = _validate_reason(reason)  # NEW (S-02): validate before write
    ks = load_kill_switch(ks_path)
    ks['enabled'] = False
    ks['reason'] = reason
    ks['activated_at'] = datetime.now(timezone.utc).isoformat()
    ks['activated_by'] = activated_by
    save_kill_switch(ks, ks_path)
    return ks


def deactivate_kill_switch(ks_path: str = 'kill_switch.json',
                          activated_by: str = 'manual'):
    """Deactivate kill switch (enable bot)."""
    ks = load_kill_switch(ks_path)
    ks['enabled'] = True
    ks['reason'] = ''
    ks['activated_at'] = None
    ks['activated_by'] = activated_by
    save_kill_switch(ks, ks_path)
    return ks


def get_full_status(ks_path: str = 'kill_switch.json') -> dict:
    """Get full kill switch status for dashboard display."""
    ks = load_kill_switch(ks_path)
    l1_enabled = os.environ.get('BOT_ENABLED', 'true').lower() == 'true'
    return {
        'l1_enabled': l1_enabled,
        'l2_enabled': ks['enabled'],
        'l2_reason': ks.get('reason', ''),
        'l2_activated_at': ks.get('activated_at'),
        'l2_activated_by': ks.get('activated_by', ''),
        'is_alive': l1_enabled and ks['enabled'],
    }
