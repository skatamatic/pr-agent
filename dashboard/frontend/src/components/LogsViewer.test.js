import React from 'react';
import { render, waitFor } from '@testing-library/react';
import LogsViewer from './LogsViewer';

jest.mock('../services/api', () => ({
  __esModule: true,
  default: {
    getRepositoryNames: jest.fn().mockResolvedValue({
      data: { data: ['org/repo-a'] },
    }),
  },
}));

describe('LogsViewer', () => {
  test('fetches repository names for dropdown', async () => {
    const api = require('../services/api').default;
    render(<LogsViewer logs={[]} />);
    await waitFor(() => {
      expect(api.getRepositoryNames).toHaveBeenCalledWith({ active_only: false });
    });
  });
});
