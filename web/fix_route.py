import re

path = r'D:\NewVolumeE\Unified agentic coding harness\web\src\app\api\settings\model\route.ts'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: broken  key in DEFAULT_MODELS
content = content.replace(
    '  : [\n' +
    "    'google/gemini-3.7-flash-exp:free',\n" +
    "    'google/gemini-3.1-pro-preview',\n" +
    "    'deepseek/deepseek-r1:free',\n" +
    "    'meta-llama/llama-3.3-70b-instruct:free',\n" +
    "    'anthropic/claude-3.7-sonnet',\n" +
    "    'openai/gpt-4o',\n" +
    '  ],\n',
    '  : [\n' +
    "    'google/gemini-3.7-flash-exp:free',\n" +
    "    'google/gemini-3.1-pro-preview',\n" +
    "    'deepseek/deepseek-r1:free',\n" +
    "    'meta-llama/llama-3.3-70b-instruct:free',\n" +
    "    'anthropic/claude-3.7-sonnet',\n" +
    "    'openai/gpt-4o',\n" +
    '  ],\n'
)

# Fix 2: broken '' key in providers object
content = content.replace(
    '      : { configured: Boolean(process.env.OPENROUTER_API_KEY), models: DEFAULT_MODELS. },\n',
    '      : { configured: Boolean(process.env.OPENROUTER_API_KEY), models: DEFAULT_MODELS. },\n'
)

# Fix 3: broken '...DEFAULT_MODELS.' in fallback array
content = content.replace(
    '...DEFAULT_MODELS.,\n',
    '...DEFAULT_MODELS.,\n'
)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixes applied.')
# Show lines around the fixed areas
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()
for i, line in enumerate(lines[:85], 1):
    print(f'{i:3}: {line}', end='')
for i, line in enumerate(lines[62:85], 63):
    print(f'{i:3}: {line}', end='')
