import React, { useState, useEffect, useContext } from 'react';
import { 
  Plus, 
  Edit, 
  Trash2, 
  GitBranch, 
  Globe, 
  Settings, 
  Check, 
  X,
  AlertCircle,
  Info,
  Github,
  Cloud
} from 'lucide-react';
import api from '../services/api';
import { ToastContext } from '../contexts/ToastContext';
import ViewHeader from './ViewHeader';

const RepositoryManager = () => {
  const [repositories, setRepositories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingRepo, setEditingRepo] = useState(null);
  const [formData, setFormData] = useState({
    name: '',
    provider: 'github',
    url: '',
    is_active: true,
    monitor_prs: true,
    monitor_issues: false,
    auto_review: true,
    auto_describe: true,
    auto_improve: false
  });
  const [errors, setErrors] = useState({});
  const { showSuccess, showError } = useContext(ToastContext);

  useEffect(() => {
    fetchRepositories();
  }, []);

  const fetchRepositories = async () => {
    try {
      setLoading(true);
      const response = await api.getRepositories();
      setRepositories(response.data.data || []);
    } catch (error) {
      showError('Error', 'Failed to fetch repositories');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrors({});

    try {
      if (editingRepo) {
        await api.updateRepository(editingRepo.id, formData);
        showSuccess('Success', 'Repository updated successfully');
      } else {
        await api.createRepository(formData);
        showSuccess('Success', 'Repository added successfully');
      }
      
      resetForm();
      fetchRepositories();
    } catch (error) {
      const errorMsg = error.response?.data?.detail || 'Failed to save repository';
      showError('Error', errorMsg);
      setErrors({ general: errorMsg });
    }
  };

  const handleDelete = async (repo) => {
    if (window.confirm(`Are you sure you want to delete repository "${repo.name}"?`)) {
      try {
        await api.deleteRepository(repo.id);
        showSuccess('Success', 'Repository deleted successfully');
        fetchRepositories();
      } catch (error) {
        showError('Error', 'Failed to delete repository');
      }
    }
  };

  const resetForm = () => {
    setFormData({
      name: '',
      provider: 'github',
      url: '',
      is_active: true,
      monitor_prs: true,
      monitor_issues: false,
      auto_review: true,
      auto_describe: true,
      auto_improve: false
    });
    setEditingRepo(null);
    setShowAddForm(false);
    setErrors({});
  };

  const startEdit = (repo) => {
    setFormData({
      name: repo.name,
      provider: repo.provider,
      url: repo.url,
      is_active: repo.is_active,
      monitor_prs: repo.monitor_prs,
      monitor_issues: repo.monitor_issues,
      auto_review: repo.auto_review,
      auto_describe: repo.auto_describe,
      auto_improve: repo.auto_improve
    });
    setEditingRepo(repo);
    setShowAddForm(true);
  };

  const getProviderIcon = (provider) => {
    switch (provider) {
      case 'github':
        return <Github className="h-4 w-4" />;
      case 'azure_devops':
        return <Cloud className="h-4 w-4" />;
      default:
        return <GitBranch className="h-4 w-4" />;
    }
  };

  const getProviderColor = (provider) => {
    switch (provider) {
      case 'github':
        return 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200';
      case 'azure_devops':
        return 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200';
      default:
        return 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200';
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <ViewHeader 
        title="Repository Management"
        subtitle="Configure which repositories PR-Agent monitors and manages"
        icon={GitBranch}
        rightComponent={
          <button
            onClick={() => setShowAddForm(true)}
            className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors duration-200"
          >
            <Plus className="h-4 w-4 mr-2" />
            Add Repository
          </button>
        }
      />

      {/* Info Card */}
      <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-md p-4">
        <div className="flex items-start">
          <Info className="h-5 w-5 text-blue-600 dark:text-blue-400 mr-2 mt-0.5 flex-shrink-0" />
          <div className="text-blue-800 dark:text-blue-200 text-sm">
            <p className="font-medium mb-1">Repository Monitoring</p>
            <p>Configure which repositories PR-Agent should monitor and what actions to perform automatically. Only active repositories will be monitored for pull requests and issues.</p>
          </div>
        </div>
      </div>

      {/* Add/Edit Form */}
      {showAddForm && (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              {editingRepo ? 'Edit Repository' : 'Add New Repository'}
            </h3>
            <button
              onClick={resetForm}
              className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {errors.general && (
            <div className="mb-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-md p-3">
              <div className="flex items-center">
                <AlertCircle className="h-4 w-4 text-red-600 dark:text-red-400 mr-2" />
                <span className="text-red-800 dark:text-red-200 text-sm">{errors.general}</span>
              </div>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Repository Name
                </label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="owner/repository-name"
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Provider
                </label>
                <select
                  value={formData.provider}
                  onChange={(e) => setFormData({ ...formData, provider: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                >
                  <option value="github">GitHub</option>
                  <option value="azure_devops">Azure DevOps</option>
                </select>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Repository URL
              </label>
              <input
                type="url"
                value={formData.url}
                onChange={(e) => setFormData({ ...formData, url: e.target.value })}
                placeholder="https://github.com/owner/repository-name"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                required
              />
            </div>

            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              <label className="flex items-center">
                <input
                  type="checkbox"
                  checked={formData.is_active}
                  onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                  className="mr-2 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700 dark:text-gray-300">Active</span>
              </label>

              <label className="flex items-center">
                <input
                  type="checkbox"
                  checked={formData.monitor_prs}
                  onChange={(e) => setFormData({ ...formData, monitor_prs: e.target.checked })}
                  className="mr-2 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700 dark:text-gray-300">Monitor PRs</span>
              </label>

              <label className="flex items-center">
                <input
                  type="checkbox"
                  checked={formData.monitor_issues}
                  onChange={(e) => setFormData({ ...formData, monitor_issues: e.target.checked })}
                  className="mr-2 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700 dark:text-gray-300">Monitor Issues</span>
              </label>

              <label className="flex items-center">
                <input
                  type="checkbox"
                  checked={formData.auto_review}
                  onChange={(e) => setFormData({ ...formData, auto_review: e.target.checked })}
                  className="mr-2 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700 dark:text-gray-300">Auto Review</span>
              </label>

              <label className="flex items-center">
                <input
                  type="checkbox"
                  checked={formData.auto_describe}
                  onChange={(e) => setFormData({ ...formData, auto_describe: e.target.checked })}
                  className="mr-2 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700 dark:text-gray-300">Auto Describe</span>
              </label>

              <label className="flex items-center">
                <input
                  type="checkbox"
                  checked={formData.auto_improve}
                  onChange={(e) => setFormData({ ...formData, auto_improve: e.target.checked })}
                  className="mr-2 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-sm text-gray-700 dark:text-gray-300">Auto Improve</span>
              </label>
            </div>

            <div className="flex justify-end space-x-3 pt-4">
              <button
                type="button"
                onClick={resetForm}
                className="px-4 py-2 text-sm border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors duration-200"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="px-4 py-2 text-sm bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors duration-200"
              >
                {editingRepo ? 'Update Repository' : 'Add Repository'}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Repository List */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
        {repositories.length === 0 ? (
          <div className="p-8 text-center">
            <GitBranch className="h-12 w-12 text-gray-400 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">No repositories configured</h3>
            <p className="text-gray-500 dark:text-gray-400 mb-4">Add your first repository to start monitoring.</p>
            <button
              onClick={() => setShowAddForm(true)}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors duration-200"
            >
              Add Repository
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead className="bg-gray-50 dark:bg-gray-700">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Repository
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Provider
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Monitoring
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                {repositories.map((repo) => (
                  <tr key={repo.id} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center">
                        <div>
                          <div className="text-sm font-medium text-gray-900 dark:text-white">
                            {repo.name}
                          </div>
                          <div className="text-sm text-gray-500 dark:text-gray-400">
                            <a href={repo.url} target="_blank" rel="noopener noreferrer" className="hover:underline flex items-center">
                              <Globe className="h-3 w-3 mr-1" />
                              {repo.url}
                            </a>
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${getProviderColor(repo.provider)}`}>
                        {getProviderIcon(repo.provider)}
                        <span className="ml-1 capitalize">{repo.provider.replace('_', ' ')}</span>
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${
                        repo.is_active 
                          ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
                          : 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200'
                      }`}>
                        {repo.is_active ? <Check className="h-3 w-3 mr-1" /> : <X className="h-3 w-3 mr-1" />}
                        {repo.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                      <div className="space-y-1">
                        {repo.monitor_prs && <div className="text-xs">• Pull Requests</div>}
                        {repo.monitor_issues && <div className="text-xs">• Issues</div>}
                        {repo.auto_review && <div className="text-xs">• Auto Review</div>}
                        {repo.auto_describe && <div className="text-xs">• Auto Describe</div>}
                        {repo.auto_improve && <div className="text-xs">• Auto Improve</div>}
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                      <div className="flex items-center space-x-2">
                        <button
                          onClick={() => startEdit(repo)}
                          className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300"
                        >
                          <Edit className="h-4 w-4" />
                        </button>
                        <button
                          onClick={() => handleDelete(repo)}
                          className="text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default RepositoryManager; 