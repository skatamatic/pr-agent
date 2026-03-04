/**
 * Tests for JobsList component job deletion functionality
 */
import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import JobsList from '../JobsList';
import api from '../../services/api';
import { ToastContext } from '../../contexts/ToastContext';

// Mock the API service
jest.mock('../../services/api', () => ({
  getJobs: jest.fn(),
  getJobDeletionPreview: jest.fn(),
  deleteJob: jest.fn(),
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

describe('JobsList Component - Job Deletion', () => {
  const mockJobs = [
    {
      job_id: 'job-123',
      job_type: 'review',
      repository: 'test/repo',
      status: 'running',
      started_at: '2024-01-15T10:00:00Z',
      completed_at: null
    },
    {
      job_id: 'job-456',
      job_type: 'improve',
      repository: 'test/repo2',
      status: 'completed',
      started_at: '2024-01-15T12:00:00Z',
      completed_at: '2024-01-15T13:00:00Z'
    }
  ];

  beforeEach(() => {
    jest.clearAllMocks();
    api.getJobs.mockResolvedValue({ data: { data: mockJobs } });
  });

  test('calls API on mount', async () => {
    await act(async () => {
      renderWithToastContext(<JobsList />);
    });
    
    // Wait for API call
    await waitFor(() => {
      expect(api.getJobs).toHaveBeenCalledWith({
        limit: 100,
        include_operations: true
      });
    });
  });

  test('renders jobs with actions menu', async () => {
    await act(async () => {
      renderWithToastContext(<JobsList />);
    });
    
    // Wait for the component to finish loading and rendering
    await waitFor(() => {
      // Check if the "No jobs found" message is gone (indicating jobs are loaded)
      expect(screen.queryByText('No jobs found matching the selected filters.')).not.toBeInTheDocument();
    }, { timeout: 5000 });
    
    // Now wait for the actual job to appear (look for repository name)
    await waitFor(() => {
      expect(screen.getByText('test/repo')).toBeInTheDocument();
    }, { timeout: 2000 });
    
    // Check that actions buttons are present
    const actionsButtons = screen.getAllByText('Actions');
    expect(actionsButtons).toHaveLength(1); // Only job-123 should be visible (running status)
  });

  test('shows actions menu when clicked', async () => {
    renderWithToastContext(<JobsList />);
    
    await waitFor(() => {
      expect(screen.getByText('test/repo')).toBeInTheDocument();
    });
    
    // Click first actions button
    const actionsButtons = screen.getAllByText('Actions');
    fireEvent.click(actionsButtons[0]);
    
    // Check that delete option appears
    expect(screen.getByText('Delete Job & Related Data')).toBeInTheDocument();
  });

  test('calls deletion preview API when delete is clicked', async () => {
    const mockPreviewData = {
      job_id: 'job-123',
      job_type: 'review',
      repository: 'test/repo',
      status: 'completed',
      started_at: '2024-01-15T10:00:00Z',
      operations_count: 5,
      logs_count: 12,
      cost_impact: 25.50,
      can_delete: true
    };
    
    api.getJobDeletionPreview.mockResolvedValue({ data: { data: mockPreviewData } });
    
    renderWithToastContext(<JobsList />);
    
    await waitFor(() => {
      expect(screen.getByText('test/repo')).toBeInTheDocument();
    });
    
    // Click actions button
    const actionsButtons = screen.getAllByText('Actions');
    fireEvent.click(actionsButtons[0]);
    
    // Click delete option
    const deleteButton = screen.getByText('Delete Job & Related Data');
    await act(async () => {
      fireEvent.click(deleteButton);
    });
    
    await waitFor(() => {
      expect(api.getJobDeletionPreview).toHaveBeenCalledWith('job-123');
    });
    
    // Check that preview dialog appears (dialog shows Job ID, Type, Operations count, Log count)
    await waitFor(() => {
      expect(screen.getByText('Delete Job & Related Data')).toBeInTheDocument();
    }, { timeout: 5000 });
    expect(screen.getByText('job-123')).toBeInTheDocument();
    expect(screen.getByText('Operations')).toBeInTheDocument();
    expect(screen.getByText('Log Entries')).toBeInTheDocument();
  });

  test('handles deletion preview API error', async () => {
    api.getJobDeletionPreview.mockRejectedValue(new Error('Preview API Error'));
    
    renderWithToastContext(<JobsList />);
    
    await waitFor(() => {
      expect(screen.getByText('test/repo')).toBeInTheDocument();
    });
    
    // Click actions button
    const actionsButtons = screen.getAllByText('Actions');
    fireEvent.click(actionsButtons[0]);
    
    // Click delete option
    const deleteButton = screen.getByText('Delete Job & Related Data');
    await act(async () => {
      fireEvent.click(deleteButton);
    });
    
    await waitFor(() => {
      expect(mockToastContext.showError).toHaveBeenCalledWith('Failed to get deletion preview: Preview API Error');
    });
  });

  test('executes job deletion when confirmed', async () => {
    const mockPreviewData = {
      job_id: 'job-123',
      job_type: 'review',
      repository: 'test/repo',
      status: 'completed',
      started_at: '2024-01-15T10:00:00Z',
      operations_count: 5,
      logs_count: 12,
      cost_impact: 25.50,
      can_delete: true
    };
    
    const mockDeleteResult = {
      job_id: 'job-123',
      operations_deleted: 5,
      logs_deleted: 12,
      job_deleted: 1,
      cost_impact: 25.50,
      repository: 'test/repo'
    };
    
    api.getJobDeletionPreview.mockResolvedValue({ data: { data: mockPreviewData } });
    api.deleteJob.mockResolvedValue({ data: mockDeleteResult });
    
    renderWithToastContext(<JobsList />);
    
    await waitFor(() => {
      expect(screen.getByText('test/repo')).toBeInTheDocument();
    });
    
    // Click actions button
    const actionsButtons = screen.getAllByText('Actions');
    fireEvent.click(actionsButtons[0]);
    
    // Click delete option
    const deleteButton = screen.getByText('Delete Job & Related Data');
    await act(async () => {
      fireEvent.click(deleteButton);
    });
    
    await waitFor(() => {
      expect(screen.getByText('Delete Job & Related Data')).toBeInTheDocument();
    }, { timeout: 5000 });
    
    
    // Click confirm delete button
    const confirmButton = screen.getByText('Delete Job & Data');
    fireEvent.click(confirmButton);
    
    await waitFor(() => {
      expect(api.deleteJob).toHaveBeenCalledWith('job-123');
    });
    
    await waitFor(() => {
      expect(mockToastContext.showSuccess).toHaveBeenCalledWith('Job and related data deleted successfully');
    });
  });

  test('handles deletion API error', async () => {
    const mockPreviewData = {
      job_id: 'job-123',
      job_type: 'review',
      repository: 'test/repo',
      status: 'completed',
      started_at: '2024-01-15T10:00:00Z',
      operations_count: 5,
      logs_count: 12,
      cost_impact: 25.50,
      can_delete: true
    };
    
    api.getJobDeletionPreview.mockResolvedValue({ data: { data: mockPreviewData } });
    api.deleteJob.mockRejectedValue(new Error('Delete API Error'));
    
    renderWithToastContext(<JobsList />);
    
    await waitFor(() => {
      expect(screen.getByText('test/repo')).toBeInTheDocument();
    });
    
    // Click actions button
    const actionsButtons = screen.getAllByText('Actions');
    fireEvent.click(actionsButtons[0]);
    
    // Click delete option
    const deleteButton = screen.getByText('Delete Job & Related Data');
    await act(async () => {
      fireEvent.click(deleteButton);
    });
    
    await waitFor(() => {
      expect(screen.getByText('Delete Job & Related Data')).toBeInTheDocument();
    }, { timeout: 5000 });
    
    // Click confirm delete button
    const confirmButton = screen.getByText('Delete Job & Data');
    fireEvent.click(confirmButton);
    
    await waitFor(() => {
      expect(mockToastContext.showError).toHaveBeenCalledWith('Failed to delete job: Delete API Error');
    });
  });

  test('cancels deletion when cancel button is clicked', async () => {
    const mockPreviewData = {
      job_id: 'job-123',
      job_type: 'review',
      repository: 'test/repo',
      status: 'completed',
      started_at: '2024-01-15T10:00:00Z',
      operations_count: 5,
      logs_count: 12,
      cost_impact: 25.50,
      can_delete: true
    };
    
    api.getJobDeletionPreview.mockResolvedValue({ data: { data: mockPreviewData } });
    
    renderWithToastContext(<JobsList />);
    
    await waitFor(() => {
      expect(screen.getByText('test/repo')).toBeInTheDocument();
    });
    
    // Click actions button
    const actionsButtons = screen.getAllByText('Actions');
    fireEvent.click(actionsButtons[0]);
    
    // Click delete option
    const deleteButton = screen.getByText('Delete Job & Related Data');
    await act(async () => {
      fireEvent.click(deleteButton);
    });
    
    await waitFor(() => {
      expect(screen.getByText('Delete Job & Related Data')).toBeInTheDocument();
    }, { timeout: 5000 });
    
    // Click cancel button
    const cancelButton = screen.getByText('Cancel');
    fireEvent.click(cancelButton);
    
    // Dialog should be closed
    await waitFor(() => {
      expect(screen.queryByText('Delete Job & Related Data')).not.toBeInTheDocument();
    });
  });

  test('shows cost impact in deletion preview', async () => {
    const mockPreviewData = {
      job_id: 'job-123',
      job_type: 'review',
      repository: 'test/repo',
      status: 'completed',
      started_at: '2024-01-15T10:00:00Z',
      operations_count: 5,
      logs_count: 12,
      cost_impact: -25.50, // Negative cost impact
      can_delete: true
    };
    
    api.getJobDeletionPreview.mockResolvedValue({ data: { data: mockPreviewData } });
    
    renderWithToastContext(<JobsList />);
    
    await waitFor(() => {
      expect(screen.getByText('test/repo')).toBeInTheDocument();
    });
    
    // Click actions button
    const actionsButtons = screen.getAllByText('Actions');
    fireEvent.click(actionsButtons[0]);
    
    // Click delete option
    const deleteButton = screen.getByText('Delete Job & Related Data');
    await act(async () => {
      fireEvent.click(deleteButton);
    });
    
    // Wait for the API call to complete
    await waitFor(() => {
      expect(api.getJobDeletionPreview).toHaveBeenCalledWith('job-123');
    });
    
    // Wait for the dialog to appear
    await waitFor(() => {
      expect(screen.getByText('Delete Job & Related Data')).toBeInTheDocument();
    }, { timeout: 3000 });
    
    // Check for cost impact (component displays absolute value with $ prefix)
    expect(screen.getByText('$25.50')).toBeInTheDocument();
  });

  test('closes actions menu when clicking outside', async () => {
    renderWithToastContext(<JobsList />);
    
    await waitFor(() => {
      expect(screen.getByText('test/repo')).toBeInTheDocument();
    });
    
    // Click actions button
    const actionsButtons = screen.getAllByText('Actions');
    fireEvent.click(actionsButtons[0]);
    
    // Check that delete option appears
    expect(screen.getByText('Delete Job & Related Data')).toBeInTheDocument();
    
    // Click outside the menu (on the document body)
    fireEvent.mouseDown(document.body);
    
    // Delete option should disappear
    await waitFor(() => {
      expect(screen.queryByText('Delete Job & Related Data')).not.toBeInTheDocument();
    });
  });
});
