import re

# Fix 1: settings_models.test.tsx - broken  key in mock object
path1 = r'D:\NewVolumeE\Unified agentic coding harness\web\__tests__\settings_models.test.tsx'
with open(path1, 'r', encoding='utf-8') as f:
    content = f.read()

# Rebuild '' from chr codes to avoid any encoding issues
orkey = ''.join(chr(c) for c in [111, 112, 101, 110, 114, 111, 117, 116, 101, 114])

# Fix broken key: '  : { configured: false, models: [...] }'
broken_line = "              : { configured: false, models: ['google/gemini-2.0-flash-exp:free'] }"
fixed_line = f"              {orkey}: " + "{ configured: false, models: ['google/gemini-2.0-flash-exp:free'] }"
content = content.replace(broken_line, fixed_line)

with open(path1, 'w', encoding='utf-8') as f:
    f.write(content)

lines = content.split('\n')
print('After fix settings_models.test.tsx:')
for i in range(23, 27):
    print(f'  {i+1}: {lines[i]}')

# Fix 2: github_integration.test.tsx - duplicate 'act' import
path2 = r'D:\NewVolumeE\Unified agentic coding harness\web\__tests__\github_integration.test.tsx'
with open(path2, 'r', encoding='utf-8') as f:
    content2 = f.read()

# Remove duplicate 'act' from line 3 import
content2 = content2.replace(
    "import { render, renderHook, act } from '@testing-library/react';",
    "import { render, renderHook } from '@testing-library/react';"
)

with open(path2, 'w', encoding='utf-8') as f:
    f.write(content2)

lines2 = content2.split('\n')
print('After fix github_integration.test.tsx imports:')
for i in range(0, 5):
    print(f'  {i+1}: {lines2[i]}')
