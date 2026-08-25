""""
Fix the f-string brace issue in generate_dashboard.py indicator history JS.
Line 1673 has }} }} which breaks the f-string.
We need to remove the extra }} from all similar patterns.
"""

import re

path = '/home/z/my-project/scripts/generate_dashboard.py'

with open(path, 'r') as f:
    content = f.read()


# Find and show problematic lines
for i, line in enumerate(content.split('\n'), 1):
    if '}}' in line and '}};' in line:
        stripped = line.strip()
        brace_count = stripped.count('{{')  # count opening braces
        close_count = stripped.count('}}')  # count closing braces
        if brace_count != close_count:
            print(f'Line {i}: (open={brace_count} close={close_count}) {stripped[:100]}...')

# Strategy: Replace '} }} }}' (which produces '}} }') with '} }}' (which produces '} }')
# The extra }} breaks the f-string because }} closes the f-string prematurely.
content = content.replace('} }} }}', '} }}')

with open(path, 'w') as f:
    f.write(content)
print('Fixed! Lines changed:', content.count('\n'))
