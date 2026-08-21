'''Kill switch management — two-layer safety system.

L1: Environment variable BOT_ENABLED (GitHub Secret) — instant, no commit needed.
L2: kill_switch.json in repo — visible on dashboard, records reason.

Engine checks L1 first, then L2. If either is OFF, trading is skipped.
'''

import json
import os
from datetime import datetime, timezone


DEFAULT_KILL_SWITCH = {
    'enabled': True,
    'reason': '',
    'activated_at': None,
    'activated_by': 'system',
}


def load_kill_switch(path: str = 'kill_switch.json') -> dict:
    """Load kill switch state from JSON file."""
    DEFAULT = {'enabled': True, 'reason': '', 'activated_at': None, 'activated_by': ''}
    if not os.path.exists(path):
        return dict(DEFAULT)
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        return {**DEFAULT, **data}
    except (json.JSONDecodeError, ValueError, OSError) as e:
        print(f'[KILL_SWITCH] WARNING: Corrupted file: {e}. Using defaults.')
        return dict(DEFAULT)


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
    """Activate kill switch (disable bot)."""
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
