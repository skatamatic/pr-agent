jest.mock('../../services/api', () => ({}));

import {
  getAzureRepoKey,
  resolveSelectedRepoKey,
  deriveAzureOrganizationFromOrgUrl,
} from '../RepositoryManager';

describe('RepositoryManager helper functions', () => {
  test('getAzureRepoKey prefers id, then url, then display_name', () => {
    expect(getAzureRepoKey({ id: 42, url: 'u', display_name: 'd' })).toBe('42');
    expect(getAzureRepoKey({ url: 'https://example.test/repo' })).toBe('https://example.test/repo');
    expect(getAzureRepoKey({ display_name: 'My Repo' })).toBe('My Repo');
    expect(getAzureRepoKey({})).toBe('');
  });

  test('resolveSelectedRepoKey keeps previous key only when still present', () => {
    const repos = [
      { id: 'a', display_name: 'Repo A' },
      { id: 'b', display_name: 'Repo B' },
    ];
    expect(resolveSelectedRepoKey(repos, 'b')).toBe('b');
    expect(resolveSelectedRepoKey(repos, 'missing')).toBe('a');
    expect(resolveSelectedRepoKey(repos, '')).toBe('a');
  });

  test('resolveSelectedRepoKey returns empty for empty repos', () => {
    expect(resolveSelectedRepoKey([], 'anything')).toBe('');
    expect(resolveSelectedRepoKey(null, 'anything')).toBe('');
  });

  test('deriveAzureOrganizationFromOrgUrl handles dev.azure.com URL', () => {
    expect(deriveAzureOrganizationFromOrgUrl('https://dev.azure.com/mdt-software')).toBe('mdt-software');
    expect(deriveAzureOrganizationFromOrgUrl('https://dev.azure.com/mdt-software/Product')).toBe('mdt-software');
  });

  test('deriveAzureOrganizationFromOrgUrl handles visualstudio.com URL', () => {
    expect(deriveAzureOrganizationFromOrgUrl('https://mdt-software.visualstudio.com')).toBe('mdt-software');
    expect(deriveAzureOrganizationFromOrgUrl('https://mdt-software.visualstudio.com/Product')).toBe('mdt-software');
  });

  test('deriveAzureOrganizationFromOrgUrl returns empty string for invalid URL', () => {
    expect(deriveAzureOrganizationFromOrgUrl('not-a-valid-url')).toBe('');
    expect(deriveAzureOrganizationFromOrgUrl('')).toBe('');
  });
});
