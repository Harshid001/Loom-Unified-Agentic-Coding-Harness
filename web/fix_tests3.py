path = r'D:\NewVolumeE\Unified agentic coding harness\web\__tests__\github_integration.test.tsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_test2 = '''  it('does not persist PAT to localStorage upon authentication', async () => {
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

new_test2 = '''  it('does not persist PAT to localStorage upon authentication', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ login: 'testuser', avatar_url: '', html_url: '', public_repos: 1 }),
    });

    // Render hook outside act(), wrap the async state transition (authenticate) inside act()
    const { result } = renderHook(() => useGitHub());
    const hookResult = result;

    await act(async () => {
      await hookResult.current.authenticate('ghp_new_ephemeral_token');
    });

    // Wait for all post-authentication async state updates to flush
    await waitFor(() => {
      expect(hookResult.current.token).toBe('ghp_new_ephemeral_token');
    });
    expect(localStorage.getItem('loom_github_token')).toBeNull();
  });'''

content = content.replace(old_test2, new_test2)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print('Done. Test lines 30-50:')
lines = content.split('\n')
for i in range(29, 52):
    print(f'  {i+1}: {lines[i]}')
