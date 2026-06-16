import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import ModelCombobox from '../ModelCombobox';
import api from '../../services/api';
import { __resetAvailableModelsCacheForTests } from '../../hooks/useAvailableModels';

jest.mock('../../services/api', () => ({
  getAvailableModels: jest.fn(),
}));

const mockPayload = {
  data: {
    data: {
      providers: {
        OpenAI: [{ id: 'gpt-4o', source: 'live' }],
      },
      all_ids: ['gpt-4o'],
    },
  },
};

describe('ModelCombobox shared model list', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    __resetAvailableModelsCacheForTests();
    api.getAvailableModels.mockResolvedValue(mockPayload);
  });

  it('all comboboxes on the same page finish loading from one fetch', async () => {
    render(
      <>
        <ModelCombobox label="Default Model" value="" onChange={jest.fn()} showRefresh={false} />
        <ModelCombobox label="Reasoning Model" value="" onChange={jest.fn()} showRefresh={false} />
        <ModelCombobox label="Simple Model" value="" onChange={jest.fn()} showRefresh={false} />
      </>
    );

    await waitFor(() => {
      expect(api.getAvailableModels).toHaveBeenCalledTimes(1);
    });

    await waitFor(() => {
      expect(screen.queryByText(/Loading available models/i)).not.toBeInTheDocument();
    });

    expect(screen.getAllByPlaceholderText('Type or select a model...')).toHaveLength(3);
  });
});
