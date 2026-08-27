import json, urllib.request, subprocess
from datetime import datetime, timezone, timedelta

result = subprocess.run(['git', 'remote', 'get-url', 'origin'], capture_output=True, text=True, cwd='/home/z/my-project')
token = result.stdout.strip().replace('https://', '').split('@github.com/')[0]
THAI_TZ = timezone(timedelta(hours=7))

all_runs = []
for page in range(1, 5):
    req = urllib.request.Request(
        f'https://api.github.com/repos/manhiiautomation-gif/Smart-dca/actions/runs?per_page=100&page={page}',
        headers={'Authorization': f'token {token}'}
    )
    resp = urllib.request.urlopen(req)
    data = json.loads(resp.read().decode())
    runs = data.get('workflow_runs', [])
    if not runs:
        break
    all_runs.extend(runs)

print('=== ALL Bitkub DCA runs ===')
for r in all_runs:
    if 'Bitkub' in r['name']:
        utc = datetime.fromisoformat(r['created_at'].replace('Z', '+00:00'))
        thai = utc.astimezone(THAI_TZ)
        print(f"  {thai.strftime('%Y-%m-%d %H:%M')} | {r['event']:15s} | {r.get('conclusion','-'):10s} | run#{r['run_number']}")

print()
print('=== Days with TEST runs ===')
all_dates = set()
bitkub_dates = set()
test_dates = set()
for r in all_runs:
    utc = datetime.fromisoformat(r['created_at'].replace('Z', '+00:00'))
    thai = utc.astimezone(THAI_TZ)
    d = thai.strftime('%Y-%m-%d')
    all_dates.add(d)
    if 'Bitkub' in r['name'] and r['event'] == 'schedule':
        bitkub_dates.add(d)
    if 'TEST' in r['name']:
        test_dates.add(d)

for d in sorted(all_dates):
    has_test = 'YES' if d in test_dates else '  no'
    has_bitkub = 'YES' if d in bitkub_dates else '  NO'
    flag = ' << PROBLEM' if (d in test_dates and d not in bitkub_dates) else ''
    print(f'  {d} | Test: {has_test} | Bitkub: {has_bitkub}{flag}')
