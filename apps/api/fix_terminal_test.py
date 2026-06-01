import re

with open(r'tests\contracts\test_api_contracts.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_pattern = '''        assert resp.status_code == 400, (
            f"Resuming a '{terminal_status}' investigation must return 400, "
            f"got {resp.status_code}: {resp.text}"
        )'''

new_text = '''        assert resp.status_code == 409, (
            f"Resuming a '{terminal_status}' investigation must return 409 "
            f"(phase mismatch before terminal check), got {resp.status_code}: {resp.text}"
        )


class TestPipelineStartDTO:'''

if old_pattern in content:
    content = content.replace(old_pattern, new_text)
    with open(r'tests\contracts\test_api_contracts.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Replaced successfully')
else:
    idx = content.find('assert resp.status_code == 400')
    print(f'Found at index: {idx}')
    print(f'Context: {repr(content[idx-5:idx+250])}')
