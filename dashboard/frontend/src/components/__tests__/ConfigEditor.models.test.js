import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ModelCombobox from '../ModelCombobox';
import api from '../../services/api';
import { __resetAvailableModelsCacheForTests } from '../../hooks/useAvailableModels';

jest.mock('../../services/api', () => ({
  getAvailableModels: jest.fn(),
  testModel: jest.fn(),
}));

describe('ConfigEditor model test panel', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    __resetAvailableModelsCacheForTests();
    api.getAvailableModels.mockResolvedValue({
      data: { data: { providers: {}, all_ids: ['gpt-4o'] } },
    });
  });

  const ModelTestPanel = ({ onTest, loading, result, model, setModel }) => (
    <div>
      <ModelCombobox
        label="Model to benchmark"
        value={model}
        onChange={setModel}
        showRefresh={false}
      />
      <button type="button" onClick={onTest} disabled={loading || !model}>
        Test Model
      </button>
      {result && (
        <div data-testid="result">
          <span>{result.message}</span>
          {result.details?.output_tokens_per_sec != null && (
            <span>Output tokens/sec: {result.details.output_tokens_per_sec}</span>
          )}
        </div>
      )}
    </div>
  );

  it('disables test button without model', () => {
    render(
      <ModelTestPanel
        onTest={jest.fn()}
        loading={false}
        result={null}
        model=""
        setModel={jest.fn()}
      />
    );
    expect(screen.getByRole('button', { name: /Test Model/i })).toBeDisabled();
  });

  it('shows success metrics from benchmark API', async () => {
    api.testModel.mockResolvedValue({
      data: {
        success: true,
        latency_ms: 1200,
        input_tokens: 900,
        output_tokens: 150,
        output_tokens_per_sec: 125,
        total_tokens_per_sec: 875,
      },
    });

    const Harness = () => {
      const [model, setModel] = React.useState('gpt-4o');
      const [loading, setLoading] = React.useState(false);
      const [result, setResult] = React.useState(null);
      const onTest = async () => {
        setLoading(true);
        const response = await api.testModel({ model });
        setResult({ message: 'Model benchmark completed.', details: response.data });
        setLoading(false);
      };
      return (
        <ModelTestPanel
          onTest={onTest}
          loading={loading}
          result={result}
          model={model}
          setModel={setModel}
        />
      );
    };

    render(<Harness />);
    await waitFor(() => {
      expect(screen.getByPlaceholderText('Type or select a model...')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /Test Model/i }));

    await waitFor(() => {
      expect(screen.getByText(/Output tokens\/sec: 125/i)).toBeInTheDocument();
    });
  });

  it('shows error card on API failure', async () => {
    api.testModel.mockRejectedValue({
      response: { data: { error: 'rate limited' } },
    });

    const Harness = () => {
      const [model, setModel] = React.useState('gpt-4o');
      const [result, setResult] = React.useState(null);
      const onTest = async () => {
        try {
          await api.testModel({ model });
        } catch (error) {
          setResult({ message: error.response.data.error });
        }
      };
      return (
        <ModelTestPanel
          onTest={onTest}
          loading={false}
          result={result}
          model={model}
          setModel={setModel}
        />
      );
    };

    render(<Harness />);
    await waitFor(() => {
      expect(screen.getByPlaceholderText('Type or select a model...')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /Test Model/i }));

    await waitFor(() => {
      expect(screen.getByText(/rate limited/i)).toBeInTheDocument();
    });
  });
});
