import React, { act } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ModelSettingsPage, { ModelSettingsContent } from '../src/app/settings/models/page';
import { POST as detectHandler } from '../src/app/api/models/detect/route';
import { GET as getSettingsHandler, PUT as putSettingsHandler } from '../src/app/api/settings/model/route';
import { NextRequest } from 'next/server';

describe('ModelSettingsPage', () => {
  beforeEach(() => {
    vi.stubEnv('NODE_ENV', 'development');
    // Mock global fetch
    global.fetch = vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (url.includes('/api/settings/model') && (!options || options.method === 'GET')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            active_model: 'claude-3-5-sonnet-20241022',
            available_models: ['claude-3-5-sonnet-20241022', 'gpt-4o'],
            providers: {
              anthropic: { configured: true, models: ['claude-3-5-sonnet-20241022'] },
              openai: { configured: false, models: ['gpt-4o'] },
              deepseek: { configured: false, models: ['deepseek-v3'] },
              gemini: { configured: false, models: ['gemini-1.5-pro'] },
              openrouter: { configured: false, models: ['google/gemini-2.0-flash-exp:free'] },
            },
          }),
        });
      }
      if (url.includes('/api/models/detect')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            valid: true,
            provider: 'anthropic',
            models: ['claude-3-5-sonnet-20241022', 'claude-3-7-sonnet-20250219'],
          }),
        });
      }
      if (url.includes('/api/settings/model') && options?.method === 'PUT') {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            active_model: 'gpt-4o',
            status: 'ok',
          }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({}),
      });
    }) as any;
  });

  it('renders provider tabs and main controls', async () => {
    await act(async () => {
      render(<ModelSettingsContent />);
    });

    // Wait for the async fetchConfig useEffect to resolve and state to settle
    await waitFor(() => {
      expect(screen.getByText(/Model Settings/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/Runtime Model Detection & Switching/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Anthropic/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/OpenAI/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/DeepSeek/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Google Gemini/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/Test & Detect/i)).toBeInTheDocument();
  });

  it('switches provider tab when clicked', async () => {
    await act(async () => {
      render(<ModelSettingsContent />);
    });

    // Wait for async fetchConfig to complete before interacting
    await waitFor(() => {
      expect(screen.getByText(/Model Settings/i)).toBeInTheDocument();
    });

    const openAiTabs = screen.getAllByText('OpenAI');
    await act(async () => {
      fireEvent.click(openAiTabs[0]);
    });

    expect(screen.getByText(/OpenAI Authentication/i)).toBeInTheDocument();
    expect(screen.getByText(/Detected OpenAI Models/i)).toBeInTheDocument();
  });

  it('handles test & detect flow with feedback', async () => {
    await act(async () => {
      render(<ModelSettingsContent />);
    });

    // Wait for initial fetchConfig to resolve
    await waitFor(() => {
      expect(screen.getByText(/Model Settings/i)).toBeInTheDocument();
    });

    const input = screen.getByPlaceholderText(/sk-ant-api03/i);
    await act(async () => {
      fireEvent.change(input, { target: { value: 'sk-ant-test-key-12345' } });
    });

    const detectBtn = screen.getByText(/Test & Detect/i);
    await act(async () => {
      fireEvent.click(detectBtn);
    });

    await waitFor(() => {
      expect(screen.getByText(/Successfully validated Anthropic key/i)).toBeInTheDocument();
    });
  });

  it('protects ModelSettingsPage behind AuthGate', async () => {
    await act(async () => {
      render(<ModelSettingsPage />);
    });

    await waitFor(() => {
      expect(screen.getByText(/Loom Dashboard/i)).toBeInTheDocument();
      expect(screen.getByPlaceholderText(/Enter master token or API key/i)).toBeInTheDocument();
    });
  });
});

describe('Next.js Model Settings API Routes', () => {
  beforeEach(() => {
    vi.stubEnv('NODE_ENV', 'development');
  });

  it('proxies detect request correctly', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      status: 200,
      json: async () => ({ valid: true, models: ['claude-3-5-sonnet-20241022'] }),
    } as any);

    const req = new NextRequest('http://localhost:3000/api/models/detect', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        origin: 'http://localhost:3000',
      },
      body: JSON.stringify({ provider: 'anthropic', api_key: 'sk-ant-test' }),
    });

    const res = await detectHandler(req);
    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.valid).toBe(true);
  });

  it('proxies GET and PUT settings correctly', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      status: 200,
      json: async () => ({ active_model: 'gpt-4o', status: 'ok' }),
    } as any);

    const getReq = new NextRequest('http://localhost:3000/api/settings/model', {
      method: 'GET',
      headers: { origin: 'http://localhost:3000' },
    });
    const getRes = await getSettingsHandler(getReq);
    expect(getRes.status).toBe(200);

    const putReq = new NextRequest('http://localhost:3000/api/settings/model', {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        origin: 'http://localhost:3000',
      },
      body: JSON.stringify({ model: 'gpt-4o' }),
    });
    const putRes = await putSettingsHandler(putReq);
    expect(putRes.status).toBe(200);
  });
});
