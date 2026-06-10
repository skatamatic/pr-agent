import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ModelCombobox from '../ModelCombobox';
import api from '../../services/api';
import { __resetAvailableModelsCacheForTests } from '../../hooks/useAvailableModels';

jest.mock('../../services/api', () => ({
  getAvailableModels: jest.fn(),
}));

async function waitForOverrideInput() {
  await waitFor(() => {
    expect(screen.getByPlaceholderText('Use default model')).toBeInTheDocument();
  });
}

describe('PrAgentConfigEditor custom model strings', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    __resetAvailableModelsCacheForTests();
    api.getAvailableModels.mockResolvedValue({
      data: { data: { providers: {}, all_ids: [] } },
    });
  });

  it('ModelCombobox accepts custom model strings for repo overrides', async () => {
    const onChange = jest.fn();
    render(
      <ModelCombobox
        label="Override Model"
        value=""
        onChange={onChange}
        allowEmpty
        emptyLabel="Use default model"
        showRefresh={false}
      />
    );

    await waitForOverrideInput();
    const input = screen.getByPlaceholderText('Use default model');
    fireEvent.change(input, { target: { value: 'anthropic/claude-custom' } });
    await waitFor(() => expect(onChange).toHaveBeenCalledWith('anthropic/claude-custom'), { timeout: 1000 });
  });

  it('allows clearing override via empty string', async () => {
    const onChange = jest.fn();
    render(
      <ModelCombobox
        label="Override Model"
        value="gpt-4o"
        onChange={onChange}
        allowEmpty
        emptyLabel="Use default model"
        showRefresh={false}
      />
    );

    await waitForOverrideInput();
    const input = screen.getByDisplayValue('gpt-4o');
    fireEvent.change(input, { target: { value: '' } });
    await waitFor(() => expect(onChange).toHaveBeenCalledWith(''), { timeout: 1000 });
  });
});
