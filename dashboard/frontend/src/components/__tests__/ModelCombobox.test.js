import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ModelCombobox from '../ModelCombobox';
import api from '../../services/api';
import { __resetAvailableModelsCacheForTests } from '../../hooks/useAvailableModels';

jest.mock('../../services/api', () => ({
  getAvailableModels: jest.fn(),
}));

async function waitForModelsLoaded() {
  await waitFor(() => {
    expect(screen.getByPlaceholderText('Type or select a model...')).toBeInTheDocument();
  });
}

describe('ModelCombobox', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    __resetAvailableModelsCacheForTests();
    api.getAvailableModels.mockResolvedValue({
      data: {
        data: {
          providers: {
            OpenAI: [{ id: 'gpt-4o', source: 'live' }],
          },
          all_ids: ['gpt-4o'],
        },
      },
    });
  });

  it('renders saved custom value not in discovered list', async () => {
    render(
      <ModelCombobox
        label="Model"
        value="custom/my-model"
        onChange={jest.fn()}
        showRefresh={false}
      />
    );

    await waitFor(() => {
      expect(screen.getByDisplayValue('custom/my-model')).toBeInTheDocument();
    });
    expect(screen.getByText(/Custom model/i)).toBeInTheDocument();
  });

  it('calls onChange when typing arbitrary string', async () => {
    const onChange = jest.fn();
    render(
      <ModelCombobox
        label="Model"
        value=""
        onChange={onChange}
        showRefresh={false}
      />
    );

    await waitForModelsLoaded();
    const input = screen.getByPlaceholderText('Type or select a model...');
    fireEvent.change(input, { target: { value: 'my/new-model' } });
    await waitFor(() => expect(onChange).toHaveBeenCalledWith('my/new-model'), { timeout: 1000 });
  });

  it('shows refresh control when enabled', async () => {
    render(
      <ModelCombobox
        label="Model"
        value=""
        onChange={jest.fn()}
      />
    );

    await waitFor(() => expect(api.getAvailableModels).toHaveBeenCalledTimes(1));
    expect(screen.getByTitle('Refresh model list')).toBeInTheDocument();
  });

  it('refresh button re-fetches models', async () => {
    render(
      <ModelCombobox
        label="Model"
        value=""
        onChange={jest.fn()}
      />
    );

    await waitForModelsLoaded();
    expect(api.getAvailableModels).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTitle('Refresh model list'));
    await waitFor(() => expect(api.getAvailableModels).toHaveBeenCalledTimes(2));
    expect(api.getAvailableModels.mock.calls[1][0]).toBe(true);
  });

  it('shows provider status when enabled', async () => {
    api.getAvailableModels.mockResolvedValue({
      data: {
        data: {
          providers: { OpenAI: [{ id: 'gpt-4o', source: 'live' }] },
          all_ids: ['gpt-4o'],
          provider_status: { openai: 'configured' },
          provider_errors: {},
        },
      },
    });

    render(
      <ModelCombobox
        label="Model"
        value=""
        onChange={jest.fn()}
        showProviderStatus
        showRefresh={false}
      />
    );

    await waitFor(() => {
      expect(screen.getByText(/openai: Connected/i)).toBeInTheDocument();
    });
  });

  it('respects disabled state', async () => {
    render(
      <ModelCombobox
        label="Model"
        value="gpt-4o"
        onChange={jest.fn()}
        disabled
        showRefresh={false}
      />
    );

    await waitForModelsLoaded();
    const input = screen.getByPlaceholderText('Type or select a model...');
    expect(input).toBeDisabled();
  });
});
