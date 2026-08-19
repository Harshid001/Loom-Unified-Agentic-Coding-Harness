path = r'D:\NewVolumeE\Unified agentic coding harness\web\__tests__\github_integration.test.tsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: Add waitFor to imports
content = content.replace(
    "import { render, renderHook } from '@testing-library/react';",
    "import { render, renderHook, waitFor } from '@testing-library/react';"
)

# Fix 2: Fix renderHook result access - use ref callback pattern
old_test2 = '''  it('does not persist PAT to localStorage upon authentication', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ login: 'testuser', avatar_url: '', html_url: '', public_repos: 1 }),
    });

    let hookResult: { current: ReturnType<typeof useGitHub> } | undefined;
    await act(async () => {
      hookResult = renderHook(() => useGitHub()).result;
      await hookResult.current.authenticate('ghp_new_ephemeral_token');
    });

    // Wait for all post-authentication async state updates to flush
    await waitFor(() => {
      expect(hookResult!.current.token).toBe('ghp_new_ephemeral_token');
    });
    expect(localStorage.getItem('loom_github_token')).toBeNull();
  });'''

new_test2 = '''  it('does not persist PAT to localStorage upon authentication', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ login: 'testuser', avatar_url: '', html_url: '', public_repos: 1 }),
    });

    let hookResult: { current: ReturnType<typeof useGitHub> } | undefined;
    await act(async () => {
      const { result } = renderHook(() => useGitHub());
      hookResult = result;
      await result.current.authenticate('ghp_new_ephemeral_token');
    });

    // Wait for all post-authentication async state updates to flush
    await waitFor(() => {
      expect(hookResult!.current.token).toBe('ghp_new_ephemeral_token');
    });
    expect(localStorage.getItem('loom_github_token')).toBeNull();
  });'''

content = content.replace(old_test2, new_test2)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

lines = content.split('\n')
print('Fixes applied. Key imports and test lines:')
for i, line in enumerate(lines[:8], 1):
    print(f'  {i}: {line}')
for i, line in enumerate(lines[30:45], 31):
    print(f'  {i}: {line}')
