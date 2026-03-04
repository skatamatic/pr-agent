/**
 * Tests for DataCleanup component
 */
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DataCleanup from '../DataCleanup';
import api from '../../services/api';
import { ToastContext } from '../../contexts/ToastContext';

// Mock the API service
jest.mock('../../services/api', () => ({
  getRepositories: jest.fn(),
  previewCleanup: jest.fn(),
  executeCleanup: jest.fn(),
}));

// Mock the ToastContext
const mockToastContext = {
  showError: jest.fn(),
  showSuccess: jest.fn(),
};

const renderWithToastContext = (component) => {
  return render(
    <ToastContext.Provider value={mockToastContext}>
      {component}
    </ToastContext.Provider>
  );
};

describe('DataCleanup Component', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    // Mock successful API responses (component uses response.data?.data, repo.name)
    api.getRepositories.mockResolvedValue({
      data: {
        data: [
          { id: 1, name: 'test/repo1' },
          { id: 2, name: 'test/repo2' }
        ]
      }
    });
    
    // Mock preview cleanup response (component uses response.data?.data)
    const mockPreviewData = {
      cutoff_date: '2024-01-15T00:00:00.000Z',
      repository: null,
      before_cleanup: {
        operations: 15,
        jobs: 5,
        logs: 25,
        notification_events: 8,
        cost_savings: 100.50
      },
      after_cleanup: {
        operations: 5,
        jobs: 3,
        logs: 5,
        notification_events: 3,
        cost_savings: 85.00
      },
      deleted_counts: {
        operations: 10,
        jobs: 2,
        logs: 20,
        notification_events: 5
      },
      to_be_deleted: {
        operations: 10,
        jobs: 2,
        logs: 20,
        notification_events: 5
      },
      cost_impact: -15.50,
      storage_impact_mb: 10.2,
      message: 'Preview generated successfully'
    };
    api.previewCleanup.mockResolvedValue({ data: { data: mockPreviewData } });

    // Mock execute cleanup response
    api.executeCleanup.mockResolvedValue({
      data: {
        cutoff_date: '2024-01-15T00:00:00.000Z',
        repository: null,
        deleted_counts: {
          operations: 10,
          jobs: 2,
          logs: 20,
          notification_events: 5
        },
        backup_path: '/tmp/test_backup.db.gz',
        message: 'Data cleanup completed successfully'
      }
    });
  });

  test('renders cleanup form with all sections', () => {
    renderWithToastContext(<DataCleanup />);
    
    expect(screen.getByText('Data Cleanup')).toBeInTheDocument();
    expect(screen.getByText('Repository Scope')).toBeInTheDocument();
    expect(screen.getByText('Cleanup Date')).toBeInTheDocument();
    expect(screen.getByText('Preview Cleanup')).toBeInTheDocument();
  });

  test('allows selecting cleanup scope', async () => {
    renderWithToastContext(<DataCleanup />);
    
    const allReposButton = screen.getByText('All Repositories');
    expect(allReposButton).toBeInTheDocument();
    
    await waitFor(() => {
      expect(screen.getByText('test/repo1')).toBeInTheDocument();
    });
    const repoLabel = screen.getByText('test/repo1');
    const repoButton = repoLabel.closest('button');
    fireEvent.click(repoButton);
    expect(repoButton).toHaveClass('bg-blue-600');
  });

  test('renders date and preview button', () => {
    renderWithToastContext(<DataCleanup />);
    
    expect(screen.getByLabelText('Date')).toBeInTheDocument();
    expect(screen.getByLabelText('Time (UTC)')).toBeInTheDocument();
    expect(screen.getByText('Preview Cleanup')).toBeInTheDocument();
  });

  test('shows preview button when date is selected', () => {
    renderWithToastContext(<DataCleanup />);
    
    const previewButton = screen.getByText('Preview Cleanup');
    expect(previewButton).toBeDisabled();
    
    const dateInput = screen.getByLabelText('Date');
    fireEvent.change(dateInput, { target: { value: '2024-01-15' } });
    
    expect(previewButton).not.toBeDisabled();
  });

  test('calls preview API with correct data', async () => {
    renderWithToastContext(<DataCleanup />);
    
    // Set date and time
    const dateInput = screen.getByLabelText('Date');
    fireEvent.change(dateInput, { target: { value: '2024-01-15' } });
    
    const timeInput = screen.getByLabelText('Time (UTC)');
    fireEvent.change(timeInput, { target: { value: '00:00' } });
    
    const previewButton = screen.getByText('Preview Cleanup');
    fireEvent.click(previewButton);
    
    await waitFor(() => {
      expect(api.previewCleanup).toHaveBeenCalledWith({
        cutoff_date: expect.stringMatching(/2024-01-15T\d{2}:00:00\.000Z/),
        repository: null
      });
    });
  });

  test('shows preview results after successful API call', async () => {
    renderWithToastContext(<DataCleanup />);
    
    // Set date and get preview
    const dateInput = screen.getByLabelText('Date');
    fireEvent.change(dateInput, { target: { value: '2024-01-15' } });
    
    const previewButton = screen.getByText('Preview Cleanup');
    fireEvent.click(previewButton);
    
    await waitFor(() => {
      expect(screen.getByText('Cleanup Impact Preview')).toBeInTheDocument();
      expect(screen.getByText('Before Cleanup')).toBeInTheDocument();
      expect(screen.getByText('After Cleanup')).toBeInTheDocument();
    });
  });

  test('shows proceed button after preview', async () => {
    renderWithToastContext(<DataCleanup />);
    
    const dateInput = screen.getByLabelText('Date');
    fireEvent.change(dateInput, { target: { value: '2024-01-15' } });
    
    const previewButton = screen.getByText('Preview Cleanup');
    fireEvent.click(previewButton);
    
    await waitFor(() => {
      expect(screen.getByText('Proceed with Cleanup')).toBeInTheDocument();
    }, { timeout: 5000 });
  });

  test('shows confirmation dialog when proceed is clicked', async () => {
    renderWithToastContext(<DataCleanup />);
    
    const dateInput = screen.getByLabelText('Date');
    fireEvent.change(dateInput, { target: { value: '2024-01-15' } });
    
    const previewButton = screen.getByText('Preview Cleanup');
    fireEvent.click(previewButton);
    
    await waitFor(() => {
      expect(screen.getByText('Proceed with Cleanup')).toBeInTheDocument();
    }, { timeout: 5000 });
    
    const proceedButton = screen.getByText('Proceed with Cleanup');
    fireEvent.click(proceedButton);
    
    await waitFor(() => {
      expect(screen.getByText('Confirmation Required')).toBeInTheDocument();
    });
    expect(screen.getByText('Execute Cleanup')).toBeInTheDocument();
  });

  test('executes cleanup when all confirmations are checked', async () => {
    renderWithToastContext(<DataCleanup />);
    
    const dateInput = screen.getByLabelText('Date');
    fireEvent.change(dateInput, { target: { value: '2024-01-15' } });
    
    const previewButton = screen.getByText('Preview Cleanup');
    fireEvent.click(previewButton);
    
    await waitFor(() => {
      expect(screen.getByText('Proceed with Cleanup')).toBeInTheDocument();
    }, { timeout: 5000 });
    
    fireEvent.click(screen.getByText('Proceed with Cleanup'));
    
    await waitFor(() => {
      expect(screen.getByText('Confirmation Required')).toBeInTheDocument();
    });
    
    // Check all confirmations
    const understandCheckbox = screen.getByLabelText('I understand this action cannot be undone');
    const backedUpCheckbox = screen.getByLabelText('I have backed up any important data');
    const proceedCheckbox = screen.getByLabelText('I want to proceed with the cleanup');
    
    fireEvent.click(understandCheckbox);
    fireEvent.click(backedUpCheckbox);
    fireEvent.click(proceedCheckbox);
    
    const executeButton = screen.getByText('Execute Cleanup');
    fireEvent.click(executeButton);
    
    await waitFor(() => {
      expect(api.executeCleanup).toHaveBeenCalledWith({
        cutoff_date: expect.stringMatching(/2024-01-15T\d{2}:00:00\.000Z/),
        repository: null,
        data_types: ['operations', 'jobs', 'logs', 'metrics', 'notification_events']
      });
    });
  });

  test('handles API errors gracefully', async () => {
    api.previewCleanup.mockRejectedValueOnce(new Error('API Error'));
    
    renderWithToastContext(<DataCleanup />);
    
    const dateInput = screen.getByLabelText('Date');
    fireEvent.change(dateInput, { target: { value: '2024-01-15' } });
    
    const previewButton = screen.getByText('Preview Cleanup');
    fireEvent.click(previewButton);
    
    await waitFor(() => {
      expect(mockToastContext.showError).toHaveBeenCalledWith('Failed to get cleanup preview: API Error');
    });
  });

  // Note: Date validation test is skipped as it's difficult to trigger invalid Date objects
  // in the test environment due to browser date input validation
});