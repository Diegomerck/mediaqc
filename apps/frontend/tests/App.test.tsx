import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import App from '../src/App';

test('the empty shell has an accessible application heading', () => {
  render(<App />);

  expect(
    screen
      .getByRole('main')
      .contains(screen.getByRole('heading', { level: 1, name: 'MediaQC' })),
  ).toBe(true);
  expect(screen.queryByRole('button')).toBeNull();
});
