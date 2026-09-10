import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, test, vi } from 'vitest';
import App from '../src/App';
import { engine, type Capabilities, type EngineStatus } from '../src/engine';

vi.mock('../src/engine', async (original) => ({
  ...(await original<typeof import('../src/engine')>()),
  engine: { status: vi.fn(), start: vi.fn(), ping: vi.fn(), stop: vi.fn() },
}));
const capabilities: Capabilities = {
  engine_version: '0.0.0',
  protocol_version: '1.0',
  schema_version: 1,
  platform: 'windows',
  ffmpeg: { available: false, version: null },
  ffprobe: { available: false, version: null },
  ai: { local_available: false, provider: null },
  detectors: [],
};
const stopped: EngineStatus = {
  phase: 'stopped',
  pid: null,
  capabilities: null,
  error: null,
  log_path: 'C:/logs/engine.log',
  desktop_version: '0.0.0',
};
const ready: EngineStatus = {
  ...stopped,
  phase: 'ready',
  pid: 123,
  capabilities,
};
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(engine.status).mockResolvedValue(stopped);
});

test('the shell has an accessible heading and gates ping until startup succeeds', async () => {
  render(<App />);
  expect(
    screen
      .getByRole('main')
      .contains(screen.getByRole('heading', { level: 1, name: 'MediaQC' })),
  ).toBe(true);
  expect(
    screen
      .getByRole('button', { name: 'Send system.ping' })
      .hasAttribute('disabled'),
  ).toBe(true);
  await screen.findByText('Engine: stopped');
  expect(engine.start).not.toHaveBeenCalled();
});

test('launch, capabilities, ping and graceful shutdown are visible', async () => {
  vi.mocked(engine.start).mockImplementation(() => {
    vi.mocked(engine.status).mockResolvedValue(ready);
    return Promise.resolve(capabilities);
  });
  vi.mocked(engine.ping).mockResolvedValue({ pong: true });
  vi.mocked(engine.stop).mockImplementation(() => {
    vi.mocked(engine.status).mockResolvedValue(stopped);
    return Promise.resolve({ forced: false });
  });
  render(<App />);
  await screen.findByText('Engine: stopped');
  fireEvent.click(screen.getByRole('button', { name: 'Start engine' }));
  await screen.findByText('Engine: ready');
  expect(screen.getByText('1.0')).toBeDefined();
  fireEvent.click(screen.getByRole('button', { name: 'Send system.ping' }));
  await screen.findByText('system.ping → {"pong":true}');
  await waitFor(() => {
    expect(
      screen
        .getByRole('button', { name: 'Stop engine' })
        .hasAttribute('disabled'),
    ).toBe(false);
  });
  fireEvent.click(screen.getByRole('button', { name: 'Stop engine' }));
  await screen.findByText('Engine shut down cleanly.');
  expect(engine.start).toHaveBeenCalledOnce();
  expect(engine.ping).toHaveBeenCalledOnce();
  expect(engine.stop).toHaveBeenCalledOnce();
});

test('startup error has diagnostic code and retry action', async () => {
  const failure = {
    code: 'ENGINE_START_FAILED',
    message: 'Bundled engine is missing.',
  };
  vi.mocked(engine.start).mockImplementation(() => {
    vi.mocked(engine.status).mockResolvedValue({
      ...stopped,
      phase: 'error',
      error: failure,
    });
    return Promise.reject(Object.assign(new Error(failure.message), failure));
  });
  render(<App />);
  await screen.findByText('Engine: stopped');
  fireEvent.click(screen.getByRole('button', { name: 'Start engine' }));
  expect((await screen.findByRole('alert')).textContent).toContain(
    'ENGINE_START_FAILED',
  );
  await screen.findByRole('button', { name: 'Restart engine' });
});

test('unexpected idle exit is surfaced without another command and can restart', async () => {
  vi.mocked(engine.status).mockResolvedValue(ready);
  render(<App />);
  await screen.findByText('Engine: ready');
  vi.mocked(engine.status).mockResolvedValue({
    ...stopped,
    phase: 'error',
    error: { code: 'ENGINE_EXITED', message: 'Engine exited unexpectedly.' },
  });
  expect((await screen.findByRole('alert')).textContent).toContain(
    'ENGINE_EXITED',
  );
  vi.mocked(engine.start).mockImplementation(() => {
    vi.mocked(engine.status).mockResolvedValue(ready);
    return Promise.resolve(capabilities);
  });
  fireEvent.click(screen.getByRole('button', { name: 'Restart engine' }));
  await screen.findByText('Engine: ready');
  expect(screen.queryByRole('alert')).toBeNull();
});

test('a forced shutdown is not reported as graceful', async () => {
  vi.mocked(engine.status).mockResolvedValue(ready);
  vi.mocked(engine.stop).mockResolvedValue({ forced: true });
  render(<App />);
  await screen.findByText('Engine: ready');
  fireEvent.click(screen.getByRole('button', { name: 'Stop engine' }));
  await screen.findByText(
    'Engine stopped after the graceful shutdown deadline.',
  );
});

test('missing desktop bridge is actionable', async () => {
  vi.mocked(engine.status).mockRejectedValue(new Error('bridge missing'));
  render(<App />);
  expect((await screen.findByRole('alert')).textContent).toContain(
    'DESKTOP_CONNECTION_FAILED',
  );
});
