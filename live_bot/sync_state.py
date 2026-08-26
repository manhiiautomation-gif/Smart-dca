"""Push bot state to GitHub for dashboard consumption.

After each bot run, copies state.json → btc-signal-analyzer/output/bot_state.json
and git pushes so the GitHub Pages dashboard can fetch it via raw.githubusercontent.com.
"""

import json
import os
import subprocess
import sys
from datetime import datetime


# Paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(PROJECT_ROOT, 'live_bot', 'state.json')
SIGNAL_REPO = os.path.join(os.path.dirname(PROJECT_ROOT), 'btc-signal-analyzer')
DEST_FILE = os.path.join(SIGNAL_REPO, 'output', 'bot_state.json')


def _get_github_token() -> str:
    """Extract GitHub token from my-project remote URL."""
    try:
        result = subprocess.run(
            ['git', 'config', '--get', 'remote.origin.url'],
            cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=10
        )
        url = result.stdout.strip()
        # Format: https://TOKEN@github.com/user/repo.git
        if '@' in url and 'github.com' in url:
            token = url.split('://')[1].split('@')[0]
            if token and len(token) > 10:
                return token
    except Exception:
        pass
    return os.environ.get('GITHUB_TOKEN', '')


def sync_bot_state(state: dict | None = None, verbose: bool = True) -> bool:
    """Copy bot state to btc-signal-analyzer repo and git push.
    
    Args:
        state: Bot state dict. If None, reads from STATE_FILE.
        verbose: Print status messages.
    
    Returns:
        True if push succeeded, False otherwise.
    """
    try:
        # Load state if not provided
        if state is None:
            if not os.path.exists(STATE_FILE):
                if verbose:
                    print('[SYNC] No state.json found, skipping.')
                return False
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
        
        # Ensure destination directory exists
        os.makedirs(os.path.dirname(DEST_FILE), exist_ok=True)
        
        # Write bot_state.json with timestamp
        state['_synced_at'] = datetime.utcnow().isoformat() + 'Z'
        with open(DEST_FILE, 'w') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        
        if verbose:
            print(f'[SYNC] Wrote {DEST_FILE}')
        
        # Git commit + push
        repo = SIGNAL_REPO
        if not os.path.isdir(os.path.join(repo, '.git')):
            if verbose:
                print(f'[SYNC] Not a git repo: {repo}')
            return False
        
        # Check if there are changes
        result = subprocess.run(
            ['git', 'diff', '--quiet', 'output/bot_state.json'],
            cwd=repo, capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            # Also check if file is untracked
            result2 = subprocess.run(
                ['git', 'ls-files', '--error-unmatch', 'output/bot_state.json'],
                cwd=repo, capture_output=True, text=True, timeout=30
            )
            if result2.returncode == 0:
                if verbose:
                    print('[SYNC] No changes to push.')
                return True
        
        # Add, commit
        subprocess.run(
            ['git', 'add', 'output/bot_state.json'],
            cwd=repo, capture_output=True, text=True, timeout=30
        )
        
        ts = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
        subprocess.run(
            ['git', 'commit', '-m', f'bot state sync: {ts}'],
            cwd=repo, capture_output=True, text=True, timeout=30
        )
        
        # Push with token from my-project remote
        token = _get_github_token()
        if token:
            # Build authenticated push URL
            url_result = subprocess.run(
                ['git', 'config', '--get', 'remote.origin.url'],
                cwd=repo, capture_output=True, text=True, timeout=10
            )
            base_url = url_result.stdout.strip()
            # Strip any existing credentials
            if '@' in base_url:
                base_url = 'https://' + base_url.split('@')[1]
            auth_url = base_url.replace('https://', f'https://{token}@')
            
            push_result = subprocess.run(
                ['git', 'push', auth_url, 'main'],
                cwd=repo, capture_output=True, text=True, timeout=60
            )
        else:
            push_result = subprocess.run(
                ['git', 'push', 'origin', 'main'],
                cwd=repo, capture_output=True, text=True, timeout=60
            )
        
        if push_result.returncode == 0:
            if verbose:
                print('[SYNC] Pushed bot_state.json to GitHub.')
            return True
        else:
            if verbose:
                print(f'[SYNC] Push failed: {push_result.stderr.strip()[:200]}')
            return False
            
    except Exception as e:
        if verbose:
            print(f'[SYNC] Error: {e}')
        return False


if __name__ == '__main__':
    ok = sync_bot_state()
    sys.exit(0 if ok else 1)
