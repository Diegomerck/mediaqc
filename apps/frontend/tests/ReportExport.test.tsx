import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import ReportExport from '../src/ReportExport';
import { jobs } from '../src/jobs';

vi.mock('../src/jobs', () => ({ jobs: { report: vi.fn() } }));

test.each(['HTML', 'PDF'] as const)(
  'exports saved run as %s and shows saved path',
  async (format) => {
    vi.mocked(jobs.report).mockResolvedValue({
      absolute_path: 'C:/project/reports/saved.pdf',
    });
    render(<ReportExport runId="saved-run" />);
    fireEvent.click(screen.getByRole('button', { name: `Export ${format}` }));
    expect(jobs.report).toHaveBeenCalledWith('saved-run', format);
    expect(
      await screen.findByText('C:/project/reports/saved.pdf'),
    ).toBeTruthy();
  },
);

test('failed export is explicit and permits retry', async () => {
  vi.mocked(jobs.report).mockRejectedValue({
    code: 'REPORT_FAILED',
    message: 'Disk full',
  });
  render(<ReportExport runId="saved-run" />);
  fireEvent.click(screen.getByRole('button', { name: 'Export PDF' }));
  expect((await screen.findByRole('alert')).textContent).toContain(
    'REPORT_FAILED: Disk full',
  );
  await waitFor(() => {
    expect(
      screen.getByRole<HTMLButtonElement>('button', { name: 'Export PDF' })
        .disabled,
    ).toBe(false);
  });
});
