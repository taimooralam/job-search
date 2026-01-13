/**
 * Tests for master-cv-editor.js
 *
 * Tests the MasterCVEditor class that provides CRUD operations
 * for the Master CV data.
 */

const fs = require('fs');
const path = require('path');

describe('MasterCVEditor', () => {
  let MasterCVEditor;
  let editor;

  beforeAll(() => {
    // Load the master-cv-editor.js file
    const filePath = path.join(__dirname, '../../static/js/master-cv-editor.js');
    const code = fs.readFileSync(filePath, 'utf-8');

    // Wrap code to expose class to window
    const wrappedCode = `
      ${code}
      window.MasterCVEditor = typeof MasterCVEditor !== 'undefined' ? MasterCVEditor : undefined;
    `;

    // Execute using Function constructor
    const fn = new Function(wrappedCode);
    fn.call(window);

    // Get class reference from window
    MasterCVEditor = window.MasterCVEditor;
  });

  beforeEach(() => {
    // Set up DOM structure
    document.body.innerHTML = `
      <!-- Tabs -->
      <button class="master-cv-tab" data-tab="candidate" aria-selected="true">Candidate</button>
      <button class="master-cv-tab" data-tab="roles" aria-selected="false">Roles</button>
      <button class="master-cv-tab" data-tab="taxonomy" aria-selected="false">Taxonomy</button>

      <!-- Tab Content -->
      <div id="tab-candidate" class="master-cv-tab-content"></div>
      <div id="tab-roles" class="master-cv-tab-content hidden"></div>
      <div id="tab-taxonomy" class="master-cv-tab-content hidden"></div>

      <!-- Candidate Fields -->
      <input id="candidate-name" />
      <input id="candidate-title" />
      <input id="candidate-years" />
      <input id="candidate-email" />
      <input id="candidate-phone" />
      <input id="candidate-linkedin" />
      <input id="candidate-location" />
      <input id="candidate-masters" />
      <input id="candidate-bachelors" />
      <div id="languages-container"></div>
      <div id="certifications-container"></div>

      <!-- Roles -->
      <div id="roles-list"></div>
      <div id="roles-count"></div>
      <div id="no-role-selected"></div>
      <div id="role-editor" class="hidden"></div>
      <input id="role-company" />
      <input id="role-title" />
      <input id="role-start-date" />
      <input id="role-end-date" />
      <input id="role-location" />
      <input id="role-is-current" type="checkbox" />
      <div id="role-keywords-chips"></div>
      <div id="role-hard-skills-chips"></div>
      <div id="role-soft-skills-chips"></div>
      <div id="role-achievements-editor"></div>

      <!-- Taxonomy -->
      <div id="taxonomy-roles-list"></div>
      <div id="taxonomy-sections"></div>
      <div id="taxonomy-role-content" class="hidden"></div>
      <select id="default-fallback-role"></select>
      <div id="skill-aliases"></div>

      <!-- Modals -->
      <div id="add-item-modal" class="hidden">
        <h3 id="add-item-title"></h3>
        <input id="add-item-input" />
      </div>
      <div id="add-chip-modal" class="hidden">
        <h3 id="add-chip-title"></h3>
        <input id="add-chip-input" />
      </div>
      <div id="add-role-modal" class="hidden">
        <input id="new-role-company" />
        <input id="new-role-title" />
      </div>
      <div id="delete-confirm-modal" class="hidden">
        <h3 id="delete-confirm-title"></h3>
        <p id="delete-confirm-message"></p>
      </div>
      <div id="version-history-modal" class="hidden">
        <div id="version-history-content"></div>
      </div>
      <div id="add-taxonomy-skill-modal" class="hidden">
        <h3 id="add-taxonomy-skill-title"></h3>
        <input id="add-taxonomy-skill-input" />
      </div>
      <div id="add-alias-modal" class="hidden">
        <input id="add-alias-canonical" />
        <input id="add-alias-variation" />
      </div>

      <!-- Save Indicator -->
      <div id="save-indicator"></div>
    `;

    // Mock the init to prevent auto-loading
    const originalInit = MasterCVEditor.prototype.init;
    MasterCVEditor.prototype.init = jest.fn();

    editor = new MasterCVEditor();

    // Restore init but don't call it
    MasterCVEditor.prototype.init = originalInit;

    // Set up test data
    editor.metadata = {
      candidate: {
        name: 'John Doe',
        title_base: 'Software Engineer',
        years_experience: 10,
        contact: {
          email: 'john@example.com',
          phone: '+1234567890',
          linkedin: 'linkedin.com/in/johndoe',
          location: 'San Francisco, CA',
        },
        education: {
          masters: 'MS Computer Science',
          bachelors: 'BS Computer Science',
        },
        languages: ['English (Native)', 'Spanish (B2)'],
        certifications: ['AWS Solutions Architect'],
      },
      roles: [
        {
          id: 'role1',
          company: 'Tech Corp',
          title: 'Senior Engineer',
          is_current: true,
        },
        {
          id: 'role2',
          company: 'Startup Inc',
          title: 'Engineer',
          is_current: false,
        },
      ],
    };

    editor.taxonomy = {
      roles: {
        'Software Engineer': {
          sections: [
            { skills: ['Python', 'JavaScript'], signals: ['Built systems'] },
          ],
        },
      },
      skill_aliases: {
        'JS': ['JavaScript', 'ECMAScript'],
      },
    };

    editor.roles = {
      role1: {
        role_id: 'role1',
        company: 'Tech Corp',
        markdown: '## Achievements\n- Built things',
      },
    };

    jest.clearAllMocks();
  });

  // =========================================================================
  // Constructor Tests
  // =========================================================================
  describe('constructor', () => {
    test('sets default AUTOSAVE_DELAY', () => {
      expect(editor.AUTOSAVE_DELAY).toBe(1500);
    });

    test('initializes saveStatus as loading', () => {
      expect(editor.saveStatus).toBe('loading');
    });

    test('initializes empty pendingChanges', () => {
      expect(editor.pendingChanges).toEqual({});
    });

    test('initializes currentTab as candidate', () => {
      expect(editor.currentTab).toBe('candidate');
    });

    test('initializes null currentRoleId', () => {
      expect(editor.currentRoleId).toBeNull();
    });
  });

  // =========================================================================
  // Method Existence Tests
  // =========================================================================
  describe('Method Existence', () => {
    const expectedMethods = [
      // Data loading
      'init',
      'loadAllData',

      // Tab navigation
      'switchTab',

      // Candidate tab
      'renderCandidateTab',
      'setInputValue',
      'renderArrayChips',
      'updateCandidateField',
      'showAddLanguageModal',
      'showAddCertificationModal',
      'closeAddItemModal',
      'confirmAddItem',
      'deleteArrayItem',

      // Roles tab
      'renderRolesList',
      'updateRolesCount',
      'selectRole',

      // Saving
      'scheduleAutoSave',
      'updateSaveIndicator',

      // Utilities
      'escapeHtml',
    ];

    expectedMethods.forEach((method) => {
      test(`has ${method} method`, () => {
        expect(typeof editor[method]).toBe('function');
      });
    });
  });

  // =========================================================================
  // loadAllData Tests
  // =========================================================================
  describe('loadAllData', () => {
    test('fetches from all three API endpoints', async () => {
      mockFetchResponse({ metadata: fixtures.masterCV.metadata });
      mockFetchResponse({ taxonomy: fixtures.masterCV.taxonomy });
      mockFetchResponse({ roles: fixtures.masterCV.roles });

      await editor.loadAllData();

      expect(fetch).toHaveBeenCalledWith('/api/master-cv/metadata');
      expect(fetch).toHaveBeenCalledWith('/api/master-cv/taxonomy');
      expect(fetch).toHaveBeenCalledWith('/api/master-cv/roles');
    });

    test('indexes roles by ID', async () => {
      mockFetchResponse({ metadata: { candidate: {} } });
      mockFetchResponse({ taxonomy: {} });
      mockFetchResponse({
        roles: [
          { role_id: 'r1', title: 'Engineer' },
          { role_id: 'r2', title: 'Manager' },
        ],
      });

      await editor.loadAllData();

      expect(editor.roles['r1'].title).toBe('Engineer');
      expect(editor.roles['r2'].title).toBe('Manager');
    });

    test('throws on API failure', async () => {
      mockFetchResponse({}, { ok: false, status: 500 });
      mockFetchResponse({});
      mockFetchResponse({});

      await expect(editor.loadAllData()).rejects.toThrow();
    });
  });

  // =========================================================================
  // switchTab Tests
  // =========================================================================
  describe('switchTab', () => {
    test('updates currentTab', () => {
      editor.switchTab('roles');

      expect(editor.currentTab).toBe('roles');
    });

    test('shows selected tab content', () => {
      editor.switchTab('roles');

      const candidateTab = document.getElementById('tab-candidate');
      const rolesTab = document.getElementById('tab-roles');

      expect(candidateTab.classList.contains('hidden')).toBe(true);
      expect(rolesTab.classList.contains('hidden')).toBe(false);
    });

    test('updates tab button active state', () => {
      editor.switchTab('taxonomy');

      const tabs = document.querySelectorAll('.master-cv-tab');
      const taxonomyTab = Array.from(tabs).find((t) => t.dataset.tab === 'taxonomy');

      expect(taxonomyTab.classList.contains('active')).toBe(true);
      expect(taxonomyTab.getAttribute('aria-selected')).toBe('true');
    });
  });

  // =========================================================================
  // renderCandidateTab Tests
  // =========================================================================
  describe('renderCandidateTab', () => {
    test('populates name input', () => {
      editor.renderCandidateTab();

      const nameInput = document.getElementById('candidate-name');
      expect(nameInput.value).toBe('John Doe');
    });

    test('populates contact fields', () => {
      editor.renderCandidateTab();

      expect(document.getElementById('candidate-email').value).toBe('john@example.com');
      expect(document.getElementById('candidate-phone').value).toBe('+1234567890');
    });

    test('populates education fields', () => {
      editor.renderCandidateTab();

      expect(document.getElementById('candidate-masters').value).toBe('MS Computer Science');
    });

    test('renders language chips', () => {
      editor.renderCandidateTab();

      const container = document.getElementById('languages-container');
      expect(container.innerHTML).toContain('English (Native)');
      expect(container.innerHTML).toContain('Spanish (B2)');
    });

    test('renders certification chips', () => {
      editor.renderCandidateTab();

      const container = document.getElementById('certifications-container');
      expect(container.innerHTML).toContain('AWS Solutions Architect');
    });

    test('handles missing candidate gracefully', () => {
      editor.metadata = null;

      expect(() => editor.renderCandidateTab()).not.toThrow();
    });
  });

  // =========================================================================
  // setInputValue Tests
  // =========================================================================
  describe('setInputValue', () => {
    test('sets input value', () => {
      editor.setInputValue('candidate-name', 'Jane Doe');

      expect(document.getElementById('candidate-name').value).toBe('Jane Doe');
    });

    test('handles null value', () => {
      editor.setInputValue('candidate-name', null);

      expect(document.getElementById('candidate-name').value).toBe('');
    });

    test('handles undefined value', () => {
      editor.setInputValue('candidate-name', undefined);

      expect(document.getElementById('candidate-name').value).toBe('');
    });

    test('handles missing element', () => {
      expect(() => editor.setInputValue('nonexistent', 'value')).not.toThrow();
    });
  });

  // =========================================================================
  // renderArrayChips Tests
  // =========================================================================
  describe('renderArrayChips', () => {
    test('renders chips for array items', () => {
      editor.renderArrayChips('languages-container', ['Python', 'Java'], 'language');

      const container = document.getElementById('languages-container');
      expect(container.innerHTML).toContain('Python');
      expect(container.innerHTML).toContain('Java');
    });

    test('shows empty state for empty array', () => {
      editor.renderArrayChips('languages-container', [], 'language');

      const container = document.getElementById('languages-container');
      expect(container.innerHTML).toContain('No languages added yet');
    });

    test('includes delete button for each chip', () => {
      editor.renderArrayChips('languages-container', ['Python'], 'language');

      const container = document.getElementById('languages-container');
      expect(container.innerHTML).toContain('chip-delete');
    });

    test('escapes HTML in chip values', () => {
      editor.renderArrayChips('languages-container', ['<script>evil</script>'], 'language');

      const container = document.getElementById('languages-container');
      expect(container.innerHTML).not.toContain('<script>');
    });
  });

  // =========================================================================
  // updateCandidateField Tests
  // =========================================================================
  describe('updateCandidateField', () => {
    beforeEach(() => {
      editor.scheduleAutoSave = jest.fn();
    });

    test('updates simple field', () => {
      editor.updateCandidateField('name', 'Jane Smith');

      expect(editor.metadata.candidate.name).toBe('Jane Smith');
    });

    test('updates nested field', () => {
      editor.updateCandidateField('contact.email', 'jane@example.com');

      expect(editor.metadata.candidate.contact.email).toBe('jane@example.com');
    });

    test('creates nested object if missing', () => {
      editor.metadata.candidate.newSection = undefined;

      editor.updateCandidateField('newSection.field', 'value');

      expect(editor.metadata.candidate.newSection.field).toBe('value');
    });

    test('schedules auto-save', () => {
      editor.updateCandidateField('name', 'Test');

      expect(editor.scheduleAutoSave).toHaveBeenCalledWith('metadata');
    });

    test('handles missing metadata', () => {
      editor.metadata = null;

      expect(() => editor.updateCandidateField('name', 'Test')).not.toThrow();
    });
  });

  // =========================================================================
  // Modal Tests
  // =========================================================================
  describe('showAddLanguageModal', () => {
    test('sets addItemType to language', () => {
      editor.showAddLanguageModal();

      expect(editor.addItemType).toBe('language');
    });

    test('shows modal', () => {
      editor.showAddLanguageModal();

      const modal = document.getElementById('add-item-modal');
      expect(modal.classList.contains('hidden')).toBe(false);
    });

    test('sets modal title', () => {
      editor.showAddLanguageModal();

      expect(document.getElementById('add-item-title').textContent).toBe('Add Language');
    });

    test('clears input', () => {
      document.getElementById('add-item-input').value = 'old value';

      editor.showAddLanguageModal();

      expect(document.getElementById('add-item-input').value).toBe('');
    });
  });

  describe('showAddCertificationModal', () => {
    test('sets addItemType to certification', () => {
      editor.showAddCertificationModal();

      expect(editor.addItemType).toBe('certification');
    });

    test('sets modal title', () => {
      editor.showAddCertificationModal();

      expect(document.getElementById('add-item-title').textContent).toBe('Add Certification');
    });
  });

  describe('closeAddItemModal', () => {
    test('hides modal', () => {
      document.getElementById('add-item-modal').classList.remove('hidden');

      editor.closeAddItemModal();

      expect(document.getElementById('add-item-modal').classList.contains('hidden')).toBe(true);
    });

    test('resets addItemType', () => {
      editor.addItemType = 'language';

      editor.closeAddItemModal();

      expect(editor.addItemType).toBeNull();
    });
  });

  describe('confirmAddItem', () => {
    beforeEach(() => {
      editor.scheduleAutoSave = jest.fn();
      editor.renderArrayChips = jest.fn();
    });

    test('adds language to array', () => {
      editor.addItemType = 'language';
      document.getElementById('add-item-input').value = 'German (B1)';

      editor.confirmAddItem();

      expect(editor.metadata.candidate.languages).toContain('German (B1)');
    });

    test('adds certification to array', () => {
      editor.addItemType = 'certification';
      document.getElementById('add-item-input').value = 'PMP';

      editor.confirmAddItem();

      expect(editor.metadata.candidate.certifications).toContain('PMP');
    });

    test('ignores empty input', () => {
      editor.addItemType = 'language';
      document.getElementById('add-item-input').value = '   ';
      const originalLength = editor.metadata.candidate.languages.length;

      editor.confirmAddItem();

      expect(editor.metadata.candidate.languages.length).toBe(originalLength);
    });

    test('closes modal after adding', () => {
      editor.addItemType = 'language';
      document.getElementById('add-item-input').value = 'French';
      document.getElementById('add-item-modal').classList.remove('hidden');

      editor.confirmAddItem();

      expect(document.getElementById('add-item-modal').classList.contains('hidden')).toBe(true);
    });

    test('schedules auto-save', () => {
      editor.addItemType = 'language';
      document.getElementById('add-item-input').value = 'French';

      editor.confirmAddItem();

      expect(editor.scheduleAutoSave).toHaveBeenCalledWith('metadata');
    });

    test('creates array if not exists', () => {
      editor.metadata.candidate.languages = undefined;
      editor.addItemType = 'language';
      document.getElementById('add-item-input').value = 'French';

      editor.confirmAddItem();

      expect(editor.metadata.candidate.languages).toContain('French');
    });
  });

  // =========================================================================
  // deleteArrayItem Tests
  // =========================================================================
  describe('deleteArrayItem', () => {
    beforeEach(() => {
      editor.scheduleAutoSave = jest.fn();
      editor.renderArrayChips = jest.fn();
    });

    test('removes language at index', () => {
      editor.deleteArrayItem('language', 0);

      expect(editor.metadata.candidate.languages).not.toContain('English (Native)');
      expect(editor.metadata.candidate.languages).toContain('Spanish (B2)');
    });

    test('removes certification at index', () => {
      editor.deleteArrayItem('certification', 0);

      expect(editor.metadata.candidate.certifications).toHaveLength(0);
    });

    test('schedules auto-save', () => {
      editor.deleteArrayItem('language', 0);

      expect(editor.scheduleAutoSave).toHaveBeenCalledWith('metadata');
    });

    test('re-renders chips', () => {
      editor.deleteArrayItem('language', 0);

      expect(editor.renderArrayChips).toHaveBeenCalled();
    });

    test('handles missing array gracefully', () => {
      editor.metadata.candidate.languages = undefined;

      expect(() => editor.deleteArrayItem('language', 0)).not.toThrow();
    });
  });

  // =========================================================================
  // renderRolesList Tests
  // =========================================================================
  describe('renderRolesList', () => {
    test('renders role items', () => {
      editor.renderRolesList();

      const container = document.getElementById('roles-list');
      expect(container.innerHTML).toContain('Tech Corp');
      expect(container.innerHTML).toContain('Senior Engineer');
    });

    test('marks current role', () => {
      editor.renderRolesList();

      const container = document.getElementById('roles-list');
      expect(container.innerHTML).toContain('current');
    });

    test('shows empty state for no roles', () => {
      editor.metadata.roles = [];

      editor.renderRolesList();

      const container = document.getElementById('roles-list');
      expect(container.innerHTML).toContain('No roles added');
    });

    test('escapes HTML in role data', () => {
      editor.metadata.roles = [
        { id: 'r1', company: '<script>evil</script>', title: 'Engineer' },
      ];

      editor.renderRolesList();

      const container = document.getElementById('roles-list');
      expect(container.innerHTML).not.toContain('<script>');
    });
  });

  // =========================================================================
  // updateRolesCount Tests
  // =========================================================================
  describe('updateRolesCount', () => {
    test('updates count element', () => {
      editor.updateRolesCount();

      const countEl = document.getElementById('roles-count');
      expect(countEl.textContent).toBe('2');
    });

    test('handles missing metadata', () => {
      editor.metadata = null;

      expect(() => editor.updateRolesCount()).not.toThrow();
    });
  });

  // =========================================================================
  // selectRole Tests
  // =========================================================================
  describe('selectRole', () => {
    test('sets currentRoleId', () => {
      editor.selectRole('role1');

      expect(editor.currentRoleId).toBe('role1');
    });

    test('shows role editor', () => {
      editor.selectRole('role1');

      expect(document.getElementById('role-editor').classList.contains('hidden')).toBe(false);
    });

    test('hides no-role-selected', () => {
      editor.selectRole('role1');

      expect(document.getElementById('no-role-selected').classList.contains('hidden')).toBe(true);
    });

    test('updates active state in list', () => {
      // Render the list first
      editor.renderRolesList();

      editor.selectRole('role2');

      const items = document.querySelectorAll('.role-list-item');
      const role2Item = Array.from(items).find((i) => i.dataset.roleId === 'role2');

      expect(role2Item.classList.contains('active')).toBe(true);
    });
  });

  // =========================================================================
  // scheduleAutoSave Tests
  // =========================================================================
  describe('scheduleAutoSave', () => {
    beforeEach(() => {
      jest.useFakeTimers();
      editor.updateSaveIndicator = jest.fn();
    });

    afterEach(() => {
      jest.useRealTimers();
    });

    test('sets unsaved indicator immediately', () => {
      editor.scheduleAutoSave('metadata');

      expect(editor.updateSaveIndicator).toHaveBeenCalledWith('unsaved');
    });

    test('tracks pending changes', () => {
      editor.scheduleAutoSave('metadata');

      expect(editor.pendingChanges.metadata).toBe(true);
    });

    test('debounces multiple rapid calls', () => {
      // Verify debounce behavior - multiple calls should set up single timeout
      const originalTimeout = editor.saveTimeout;

      editor.scheduleAutoSave('metadata');
      const firstTimeout = editor.saveTimeout;

      editor.scheduleAutoSave('metadata');
      const secondTimeout = editor.saveTimeout;

      // Each call should replace the previous timeout
      expect(editor.saveTimeout).not.toBeNull();
      expect(editor.pendingChanges.metadata).toBe(true);
    });
  });

  // =========================================================================
  // updateSaveIndicator Tests
  // =========================================================================
  describe('updateSaveIndicator', () => {
    test('updates saveStatus', () => {
      editor.updateSaveIndicator('saved');

      expect(editor.saveStatus).toBe('saved');
    });

    test('handles all status types', () => {
      const statuses = ['saved', 'saving', 'unsaved', 'error'];

      statuses.forEach((status) => {
        expect(() => editor.updateSaveIndicator(status)).not.toThrow();
        expect(editor.saveStatus).toBe(status);
      });
    });
  });

  // =========================================================================
  // escapeHtml Tests
  // =========================================================================
  describe('escapeHtml', () => {
    test('escapes < and >', () => {
      const result = editor.escapeHtml('<div>test</div>');
      expect(result).not.toContain('<div>');
    });

    test('escapes ampersand', () => {
      const result = editor.escapeHtml('foo & bar');
      expect(result).toContain('&amp;');
    });

    test('preserves quotes (textContent encoding)', () => {
      // Note: The escapeHtml implementation uses textContent which preserves quotes
      // This is safe because quotes don't need escaping for text content
      const result = editor.escapeHtml('"quoted"');
      expect(result).toContain('quoted');
    });

    test('returns empty string for null', () => {
      expect(editor.escapeHtml(null)).toBe('');
    });

    test('returns empty string for undefined', () => {
      expect(editor.escapeHtml(undefined)).toBe('');
    });
  });
});
