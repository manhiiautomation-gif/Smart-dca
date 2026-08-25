PATH = '/home/z/my-project/live_bot/strategy.py'

with open(PATH) as f:
    content = f.read()

for i, line in enumerate(content):
    if 'def compute_mvrv_percentile' in line:
        break

helper = '''def _get_mvrv_history(d: date, window: int = 365) -> list:
    """Gather MVRV history values for a date range. Shared by percentile and zscore."""
    values = []
    for i in range(1, window + 1):
        check = d - timedelta(days=i)
        if check in _MVRV_LOOKUP:
            values.append(_MVRV_LOOKUP[check])
        elif check < _MVRV_HISTORY_MIN:
            break
    return values

'''
if helper in content:
    print('ERROR: helper already exists')
    exit(1)

lines = content.split('\n')
insert_at = i
lines.insert(insert_at, helper)
print(f'OK: inserted helper at line {insert_at+1}')
with open(PATH, 'w') as f:
    f.write('\n'.join(lines))
print(f'Written {len(lines)} lines')
