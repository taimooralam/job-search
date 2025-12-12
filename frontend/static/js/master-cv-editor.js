/**
 * Master CV Editor
 *
 * Provides CRUD operations for the Master CV data stored in MongoDB.
 * Features:
 * - Tab-based navigation (Candidate, Roles, Taxonomy)
 * - Debounced auto-save (3 second delay)
 * - TipTap rich text editor for role achievements
 * - Version history and rollback
 * - Chip-based array field editing
 */

class MasterCVEditor {
    constructor() {
        // Configuration
        this.AUTOSAVE_DELAY = 3000; // 3 seconds

        // State
        this.saveTimeout = null;
        this.saveStatus = 'loading';
        this.pendingChanges = {};
        this.currentTab = 'candidate';

        // Cached data from MongoDB
        this.metadata = null;
        this.taxonomy = null;
        this.roles = {}; // { role_id: roleData }

        // Role editor state
        this.roleEditor = null;
        this.currentRoleId = null;
        this.currentTaxonomyRole = null;

        // Modal state
        this.addItemType = null; // 'language' or 'certification'
        this.addChipField = null; // 'keywords', 'hard_skills', etc.
        this.addTaxonomySection = null;
        this.deleteCallback = null;

        // History state
        this.currentHistoryCollection = 'metadata';

        // Initialize
        this.init();
    }

    async init() {
        console.log('Initializing Master CV Editor...');
        try {
            await this.loadAllData();
            this.setupKeyboardShortcuts();
            this.updateSaveIndicator('saved');
            console.log('Master CV Editor initialized successfully');
        } catch (error) {
            console.error('Failed to initialize Master CV Editor:', error);
            this.updateSaveIndicator('error');
        }
    }

    // ==========================================================================
    // DATA LOADING
    // ==========================================================================

    async loadAllData() {
        try {
            const [metadataRes, taxonomyRes, rolesRes] = await Promise.all([
                fetch('/api/master-cv/metadata'),
                fetch('/api/master-cv/taxonomy'),
                fetch('/api/master-cv/roles')
            ]);

            if (!metadataRes.ok || !taxonomyRes.ok || !rolesRes.ok) {
                throw new Error('Failed to load master CV data');
            }

            const metadataData = await metadataRes.json();
            const taxonomyData = await taxonomyRes.json();
            const rolesData = await rolesRes.json();

            this.metadata = metadataData.metadata;
            this.taxonomy = taxonomyData.taxonomy;

            // Index roles by ID
            if (rolesData.roles) {
                rolesData.roles.forEach(role => {
                    this.roles[role.role_id || role._id] = role;
                });
            }

            // Render all sections
            this.renderCandidateTab();
            this.renderRolesList();
            this.renderTaxonomyTab();
            this.updateRolesCount();

        } catch (error) {
            console.error('Error loading data:', error);
            throw error;
        }
    }

    // ==========================================================================
    // TAB NAVIGATION
    // ==========================================================================

    switchTab(tabName) {
        this.currentTab = tabName;

        // Update tab buttons
        document.querySelectorAll('.master-cv-tab').forEach(tab => {
            const isActive = tab.dataset.tab === tabName;
            tab.classList.toggle('active', isActive);
            tab.setAttribute('aria-selected', isActive);
        });

        // Update tab content
        document.querySelectorAll('.master-cv-tab-content').forEach(content => {
            content.classList.add('hidden');
        });
        document.getElementById(`tab-${tabName}`).classList.remove('hidden');
    }

    // ==========================================================================
    // CANDIDATE TAB
    // ==========================================================================

    renderCandidateTab() {
        if (!this.metadata?.candidate) return;

        const c = this.metadata.candidate;

        // Basic info
        this.setInputValue('candidate-name', c.name);
        this.setInputValue('candidate-title', c.title_base);
        this.setInputValue('candidate-years', c.years_experience);

        // Contact
        if (c.contact) {
            this.setInputValue('candidate-email', c.contact.email);
            this.setInputValue('candidate-phone', c.contact.phone);
            this.setInputValue('candidate-linkedin', c.contact.linkedin);
            this.setInputValue('candidate-location', c.contact.location);
        }

        // Education
        if (c.education) {
            this.setInputValue('candidate-masters', c.education.masters);
            this.setInputValue('candidate-bachelors', c.education.bachelors);
        }

        // Languages
        this.renderArrayChips('languages-container', c.languages || [], 'language');

        // Certifications
        this.renderArrayChips('certifications-container', c.certifications || [], 'certification');
    }

    setInputValue(id, value) {
        const el = document.getElementById(id);
        if (el) el.value = value ?? '';
    }

    renderArrayChips(containerId, items, type) {
        const container = document.getElementById(containerId);
        if (!container) return;

        if (items.length === 0) {
            container.innerHTML = `<span class="text-sm italic" style="color: var(--text-tertiary);">No ${type}s added yet</span>`;
            return;
        }

        container.innerHTML = items.map((item, index) => `
            <span class="master-cv-chip">
                ${this.escapeHtml(item)}
                <button class="chip-delete" onclick="masterCVEditor.deleteArrayItem('${type}', ${index})" title="Remove">
                    <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                    </svg>
                </button>
            </span>
        `).join('');
    }

    updateCandidateField(path, value) {
        if (!this.metadata) return;

        // Handle nested paths like 'contact.email'
        const parts = path.split('.');
        let obj = this.metadata.candidate;

        for (let i = 0; i < parts.length - 1; i++) {
            if (!obj[parts[i]]) obj[parts[i]] = {};
            obj = obj[parts[i]];
        }
        obj[parts[parts.length - 1]] = value;

        this.scheduleAutoSave('metadata');
    }

    // Array item management
    showAddLanguageModal() {
        this.addItemType = 'language';
        document.getElementById('add-item-title').textContent = 'Add Language';
        document.getElementById('add-item-input').placeholder = 'e.g., German (B2)';
        document.getElementById('add-item-input').value = '';
        document.getElementById('add-item-modal').classList.remove('hidden');
        document.getElementById('add-item-input').focus();
    }

    showAddCertificationModal() {
        this.addItemType = 'certification';
        document.getElementById('add-item-title').textContent = 'Add Certification';
        document.getElementById('add-item-input').placeholder = 'e.g., AWS Solutions Architect';
        document.getElementById('add-item-input').value = '';
        document.getElementById('add-item-modal').classList.remove('hidden');
        document.getElementById('add-item-input').focus();
    }

    closeAddItemModal() {
        document.getElementById('add-item-modal').classList.add('hidden');
        this.addItemType = null;
    }

    confirmAddItem() {
        const input = document.getElementById('add-item-input');
        const value = input.value.trim();

        if (!value) return;

        const field = this.addItemType === 'language' ? 'languages' : 'certifications';
        if (!this.metadata.candidate[field]) {
            this.metadata.candidate[field] = [];
        }
        this.metadata.candidate[field].push(value);

        // Re-render
        const containerId = field === 'languages' ? 'languages-container' : 'certifications-container';
        this.renderArrayChips(containerId, this.metadata.candidate[field], this.addItemType);

        this.closeAddItemModal();
        this.scheduleAutoSave('metadata');
    }

    deleteArrayItem(type, index) {
        const field = type === 'language' ? 'languages' : 'certifications';
        if (this.metadata.candidate[field]) {
            this.metadata.candidate[field].splice(index, 1);
            const containerId = field === 'languages' ? 'languages-container' : 'certifications-container';
            this.renderArrayChips(containerId, this.metadata.candidate[field], type);
            this.scheduleAutoSave('metadata');
        }
    }

    // ==========================================================================
    // ROLES TAB
    // ==========================================================================

    renderRolesList() {
        const container = document.getElementById('roles-list');
        if (!container || !this.metadata?.roles) return;

        if (this.metadata.roles.length === 0) {
            container.innerHTML = '<div class="text-sm italic p-3" style="color: var(--text-tertiary);">No roles added</div>';
            return;
        }

        container.innerHTML = this.metadata.roles.map(role => `
            <div class="role-list-item ${role.id === this.currentRoleId ? 'active' : ''} ${role.is_current ? 'current' : ''}"
                 onclick="masterCVEditor.selectRole('${role.id}')"
                 data-role-id="${role.id}">
                <span class="role-indicator"></span>
                <div class="flex-1 min-w-0">
                    <div class="font-medium text-sm truncate" style="color: inherit;">${this.escapeHtml(role.company)}</div>
                    <div class="text-xs truncate" style="color: var(--text-tertiary);">${this.escapeHtml(role.title)}</div>
                </div>
            </div>
        `).join('');
    }

    updateRolesCount() {
        const countEl = document.getElementById('roles-count');
        if (countEl && this.metadata?.roles) {
            countEl.textContent = this.metadata.roles.length;
        }
    }

    selectRole(roleId) {
        this.currentRoleId = roleId;

        // Update list selection
        document.querySelectorAll('.role-list-item').forEach(item => {
            item.classList.toggle('active', item.dataset.roleId === roleId);
        });

        // Show editor, hide empty state
        document.getElementById('no-role-selected').classList.add('hidden');
        document.getElementById('role-editor').classList.remove('hidden');

        // Find role in metadata
        const role = this.metadata.roles.find(r => r.id === roleId);
        if (!role) return;

        // Populate form fields
        this.setInputValue('role-company', role.company);
        this.setInputValue('role-title', role.title);
        this.setInputValue('role-location', role.location);
        this.setInputValue('role-period', role.period);
        this.setInputValue('role-industry', role.industry);
        this.setInputValue('role-team-size', role.team_size);
        document.getElementById('role-is-current').checked = role.is_current || false;

        // Render chip fields
        this.renderRoleChips('role-keywords', role.keywords || [], 'keywords');
        this.renderRoleChips('role-hard-skills', role.hard_skills || [], 'hard_skills');
        this.renderRoleChips('role-soft-skills', role.soft_skills || [], 'soft_skills');
        this.renderRoleChips('role-primary-competencies', role.primary_competencies || [], 'primary_competencies');

        // Load role content (markdown) from roles collection
        this.loadRoleContent(roleId);
    }

    renderRoleChips(containerId, items, field) {
        const container = document.getElementById(containerId);
        if (!container) return;

        if (items.length === 0) {
            container.innerHTML = `<span class="text-xs italic" style="color: var(--text-tertiary);">None added</span>`;
            return;
        }

        container.innerHTML = items.map((item, index) => `
            <span class="master-cv-chip">
                ${this.escapeHtml(item)}
                <button class="chip-delete" onclick="masterCVEditor.deleteRoleChip('${field}', ${index})" title="Remove">
                    <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                    </svg>
                </button>
            </span>
        `).join('');
    }

    async loadRoleContent(roleId) {
        try {
            // Check if we already have it cached
            if (this.roles[roleId]?.markdown_content) {
                this.initTipTapEditor(this.roles[roleId].markdown_content);
                return;
            }

            const res = await fetch(`/api/master-cv/roles/${roleId}`);
            if (res.ok) {
                const data = await res.json();
                if (data.role) {
                    this.roles[roleId] = data.role;
                    this.initTipTapEditor(data.role.markdown_content || '');
                }
            } else {
                // Role content doesn't exist yet
                this.initTipTapEditor('');
            }
        } catch (error) {
            console.error('Error loading role content:', error);
            this.initTipTapEditor('');
        }
    }

    initTipTapEditor(content) {
        const container = document.getElementById('role-tiptap-editor');
        if (!container) return;

        // Destroy existing editor
        if (this.roleEditor) {
            this.roleEditor.destroy();
            this.roleEditor = null;
        }

        // Check if TipTap is available
        if (typeof window.Editor === 'undefined' || typeof window.StarterKit === 'undefined') {
            // TipTap not loaded - show plain textarea fallback
            container.innerHTML = `
                <textarea id="role-markdown-textarea"
                          class="w-full h-full min-h-[300px] p-4 resize-none focus:outline-none"
                          style="background: transparent; color: var(--text-primary);"
                          onchange="masterCVEditor.updateRoleMarkdown(this.value)">${this.escapeHtml(content)}</textarea>
            `;
            return;
        }

        // Initialize TipTap
        try {
            this.roleEditor = new window.Editor({
                element: container,
                extensions: [
                    window.StarterKit,
                    window.Underline,
                ],
                content: content || '<p></p>',
                onUpdate: ({ editor }) => {
                    this.scheduleRoleMarkdownSave();
                },
            });

            // Update toolbar button states
            this.updateTipTapToolbar();
        } catch (error) {
            console.error('Error initializing TipTap:', error);
            // Fallback to textarea
            container.innerHTML = `
                <textarea id="role-markdown-textarea"
                          class="w-full h-full min-h-[300px] p-4 resize-none focus:outline-none"
                          style="background: transparent; color: var(--text-primary);"
                          onchange="masterCVEditor.updateRoleMarkdown(this.value)">${this.escapeHtml(content)}</textarea>
            `;
        }
    }

    editorCommand(command, params = {}) {
        if (this.roleEditor) {
            this.roleEditor.chain().focus()[command](params).run();
            this.updateTipTapToolbar();
        }
    }

    updateTipTapToolbar() {
        if (!this.roleEditor) return;
        // Update active states on toolbar buttons if needed
    }

    scheduleRoleMarkdownSave() {
        const indicator = document.getElementById('role-markdown-indicator');
        if (indicator) {
            indicator.textContent = 'Unsaved';
            indicator.style.color = 'var(--text-tertiary)';
        }
        this.scheduleAutoSave('role-content');
    }

    updateRoleMarkdown(content) {
        if (!this.currentRoleId) return;

        if (!this.roles[this.currentRoleId]) {
            this.roles[this.currentRoleId] = { role_id: this.currentRoleId };
        }
        this.roles[this.currentRoleId].markdown_content = content;
        this.scheduleRoleMarkdownSave();
    }

    updateRoleField(field, value) {
        if (!this.currentRoleId || !this.metadata?.roles) return;

        const roleIndex = this.metadata.roles.findIndex(r => r.id === this.currentRoleId);
        if (roleIndex === -1) return;

        this.metadata.roles[roleIndex][field] = value;

        // Update list if company changed
        if (field === 'company' || field === 'title' || field === 'is_current') {
            this.renderRolesList();
        }

        this.scheduleAutoSave('role-metadata');
    }

    showAddChipModal(field) {
        this.addChipField = field;
        const titles = {
            'keywords': 'Add Keywords',
            'hard_skills': 'Add Hard Skills',
            'soft_skills': 'Add Soft Skills',
            'primary_competencies': 'Add Competencies'
        };
        document.getElementById('add-chip-title').textContent = titles[field] || 'Add Item';
        document.getElementById('add-chip-input').value = '';
        document.getElementById('add-chip-modal').classList.remove('hidden');
        document.getElementById('add-chip-input').focus();
    }

    closeAddChipModal() {
        document.getElementById('add-chip-modal').classList.add('hidden');
        this.addChipField = null;
    }

    confirmAddChip() {
        const input = document.getElementById('add-chip-input');
        const values = input.value.split(',').map(v => v.trim()).filter(v => v);

        if (values.length === 0 || !this.addChipField || !this.currentRoleId) return;

        const roleIndex = this.metadata.roles.findIndex(r => r.id === this.currentRoleId);
        if (roleIndex === -1) return;

        if (!this.metadata.roles[roleIndex][this.addChipField]) {
            this.metadata.roles[roleIndex][this.addChipField] = [];
        }

        // Add new values
        values.forEach(v => {
            if (!this.metadata.roles[roleIndex][this.addChipField].includes(v)) {
                this.metadata.roles[roleIndex][this.addChipField].push(v);
            }
        });

        // Re-render
        const containerMap = {
            'keywords': 'role-keywords',
            'hard_skills': 'role-hard-skills',
            'soft_skills': 'role-soft-skills',
            'primary_competencies': 'role-primary-competencies'
        };
        this.renderRoleChips(containerMap[this.addChipField], this.metadata.roles[roleIndex][this.addChipField], this.addChipField);

        this.closeAddChipModal();
        this.scheduleAutoSave('role-metadata');
    }

    deleteRoleChip(field, index) {
        if (!this.currentRoleId || !this.metadata?.roles) return;

        const roleIndex = this.metadata.roles.findIndex(r => r.id === this.currentRoleId);
        if (roleIndex === -1) return;

        if (this.metadata.roles[roleIndex][field]) {
            this.metadata.roles[roleIndex][field].splice(index, 1);

            const containerMap = {
                'keywords': 'role-keywords',
                'hard_skills': 'role-hard-skills',
                'soft_skills': 'role-soft-skills',
                'primary_competencies': 'role-primary-competencies'
            };
            this.renderRoleChips(containerMap[field], this.metadata.roles[roleIndex][field], field);
            this.scheduleAutoSave('role-metadata');
        }
    }

    // Add/Delete Role
    showAddRoleModal() {
        document.getElementById('new-role-company').value = '';
        document.getElementById('new-role-title').value = '';
        document.getElementById('new-role-start-year').value = new Date().getFullYear();
        document.getElementById('new-role-end-year').value = '';
        document.getElementById('add-role-modal').classList.remove('hidden');
        document.getElementById('new-role-company').focus();
    }

    closeAddRoleModal() {
        document.getElementById('add-role-modal').classList.add('hidden');
    }

    confirmAddRole() {
        const company = document.getElementById('new-role-company').value.trim();
        const title = document.getElementById('new-role-title').value.trim();
        const startYear = parseInt(document.getElementById('new-role-start-year').value);
        const endYear = document.getElementById('new-role-end-year').value.trim();

        if (!company || !title) {
            alert('Please fill in company and title');
            return;
        }

        // Generate role ID
        const roleId = `${String(this.metadata.roles.length + 1).padStart(2, '0')}_${company.toLowerCase().replace(/[^a-z0-9]+/g, '_')}`;

        const newRole = {
            id: roleId,
            company,
            title,
            location: '',
            period: endYear ? `${startYear}-${endYear}` : `${startYear}-Present`,
            start_year: startYear,
            end_year: endYear ? parseInt(endYear) : null,
            is_current: !endYear,
            duration_years: endYear ? parseInt(endYear) - startYear : new Date().getFullYear() - startYear,
            industry: '',
            team_size: '',
            primary_competencies: [],
            keywords: [],
            hard_skills: [],
            soft_skills: [],
            achievement_themes: [],
            career_stage: 'mid'
        };

        this.metadata.roles.push(newRole);
        this.renderRolesList();
        this.updateRolesCount();
        this.closeAddRoleModal();
        this.selectRole(roleId);
        this.scheduleAutoSave('metadata');
    }

    confirmDeleteRole() {
        if (!this.currentRoleId) return;

        const role = this.metadata.roles.find(r => r.id === this.currentRoleId);
        if (!role) return;

        this.showDeleteConfirm(
            'Delete Role',
            `Are you sure you want to delete the role "${role.title}" at "${role.company}"? This will remove all associated achievements and metadata.`,
            () => {
                const index = this.metadata.roles.findIndex(r => r.id === this.currentRoleId);
                if (index > -1) {
                    this.metadata.roles.splice(index, 1);
                    delete this.roles[this.currentRoleId];
                    this.currentRoleId = null;
                    this.renderRolesList();
                    this.updateRolesCount();

                    // Show empty state
                    document.getElementById('no-role-selected').classList.remove('hidden');
                    document.getElementById('role-editor').classList.add('hidden');

                    this.scheduleAutoSave('metadata');
                }
            }
        );
    }

    // ==========================================================================
    // TAXONOMY TAB
    // ==========================================================================

    renderTaxonomyTab() {
        if (!this.taxonomy) return;

        // Populate role selector
        const selector = document.getElementById('taxonomy-role-selector');
        if (selector && this.taxonomy.target_roles) {
            const roles = Object.keys(this.taxonomy.target_roles);
            selector.innerHTML = roles.map(role => {
                const displayName = this.taxonomy.target_roles[role].display_name || role;
                return `<option value="${role}" ${role === this.currentTaxonomyRole ? 'selected' : ''}>${displayName}</option>`;
            }).join('');

            // Select first role if none selected
            if (!this.currentTaxonomyRole && roles.length > 0) {
                this.currentTaxonomyRole = roles[0];
            }
        }

        // Populate fallback role selector
        const fallbackSelector = document.getElementById('default-fallback-role');
        if (fallbackSelector && this.taxonomy.target_roles) {
            const roles = Object.keys(this.taxonomy.target_roles);
            fallbackSelector.innerHTML = roles.map(role => {
                const displayName = this.taxonomy.target_roles[role].display_name || role;
                const isSelected = role === this.taxonomy.default_fallback_role;
                return `<option value="${role}" ${isSelected ? 'selected' : ''}>${displayName}</option>`;
            }).join('');
        }

        // Render sections for current role
        this.renderTaxonomySections();

        // Render skill aliases
        this.renderSkillAliases();
    }

    selectTaxonomyRole(role) {
        this.currentTaxonomyRole = role;
        this.renderTaxonomySections();
    }

    renderTaxonomySections() {
        const container = document.getElementById('taxonomy-sections-container');
        if (!container || !this.currentTaxonomyRole || !this.taxonomy?.target_roles) return;

        const roleData = this.taxonomy.target_roles[this.currentTaxonomyRole];
        if (!roleData?.sections) {
            container.innerHTML = '<div class="text-sm italic p-4" style="color: var(--text-tertiary);">No sections defined for this role</div>';
            return;
        }

        container.innerHTML = roleData.sections.map((section, sectionIndex) => `
            <div class="taxonomy-section" data-section-index="${sectionIndex}">
                <div class="taxonomy-section-header" onclick="masterCVEditor.toggleTaxonomySection(${sectionIndex})">
                    <div class="flex items-center gap-3">
                        <span class="font-medium" style="color: var(--text-primary);">${this.escapeHtml(section.name)}</span>
                        <span class="text-xs px-2 py-0.5 rounded-full" style="background-color: var(--bg-hover); color: var(--text-tertiary);">
                            Priority: ${section.priority || '-'}
                        </span>
                    </div>
                    <svg class="chevron w-5 h-5" style="color: var(--text-tertiary);" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
                    </svg>
                </div>
                <div class="taxonomy-section-content">
                    <!-- Skills -->
                    <div class="mb-4">
                        <div class="flex items-center justify-between mb-2">
                            <label class="text-sm font-medium" style="color: var(--text-secondary);">Skills</label>
                            <button onclick="masterCVEditor.showAddTaxonomySkillModal(${sectionIndex}, 'skills')"
                                    class="btn btn-ghost btn-xs">+ Add</button>
                        </div>
                        <div class="flex flex-wrap gap-2">
                            ${(section.skills || []).map((skill, skillIndex) => `
                                <span class="master-cv-chip">
                                    ${this.escapeHtml(skill)}
                                    <button class="chip-delete" onclick="masterCVEditor.deleteTaxonomySkill(${sectionIndex}, ${skillIndex})" title="Remove">
                                        <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                                        </svg>
                                    </button>
                                </span>
                            `).join('') || '<span class="text-xs italic" style="color: var(--text-tertiary);">None</span>'}
                        </div>
                    </div>

                    <!-- JD Signals -->
                    <div>
                        <div class="flex items-center justify-between mb-2">
                            <label class="text-sm font-medium" style="color: var(--text-secondary);">JD Signals</label>
                            <button onclick="masterCVEditor.showAddTaxonomySkillModal(${sectionIndex}, 'jd_signals')"
                                    class="btn btn-ghost btn-xs">+ Add</button>
                        </div>
                        <div class="flex flex-wrap gap-2">
                            ${(section.jd_signals || []).map((signal, signalIndex) => `
                                <span class="master-cv-chip" style="font-style: italic;">
                                    "${this.escapeHtml(signal)}"
                                    <button class="chip-delete" onclick="masterCVEditor.deleteTaxonomySignal(${sectionIndex}, ${signalIndex})" title="Remove">
                                        <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                                        </svg>
                                    </button>
                                </span>
                            `).join('') || '<span class="text-xs italic" style="color: var(--text-tertiary);">None</span>'}
                        </div>
                    </div>
                </div>
            </div>
        `).join('');
    }

    toggleTaxonomySection(index) {
        const section = document.querySelector(`.taxonomy-section[data-section-index="${index}"]`);
        if (section) {
            section.classList.toggle('open');
        }
    }

    showAddTaxonomySkillModal(sectionIndex, type) {
        this.addTaxonomySection = { sectionIndex, type };
        const title = type === 'skills' ? 'Add Skill' : 'Add JD Signal';
        document.getElementById('add-taxonomy-skill-title').textContent = title;
        document.getElementById('add-taxonomy-skill-input').value = '';
        document.getElementById('add-taxonomy-skill-modal').classList.remove('hidden');
        document.getElementById('add-taxonomy-skill-input').focus();
    }

    closeAddTaxonomySkillModal() {
        document.getElementById('add-taxonomy-skill-modal').classList.add('hidden');
        this.addTaxonomySection = null;
    }

    confirmAddTaxonomySkill() {
        const input = document.getElementById('add-taxonomy-skill-input');
        const value = input.value.trim();

        if (!value || !this.addTaxonomySection || !this.currentTaxonomyRole) return;

        const { sectionIndex, type } = this.addTaxonomySection;
        const roleData = this.taxonomy.target_roles[this.currentTaxonomyRole];
        if (!roleData?.sections?.[sectionIndex]) return;

        if (!roleData.sections[sectionIndex][type]) {
            roleData.sections[sectionIndex][type] = [];
        }
        roleData.sections[sectionIndex][type].push(value);

        this.renderTaxonomySections();
        this.closeAddTaxonomySkillModal();
        this.scheduleAutoSave('taxonomy');
    }

    deleteTaxonomySkill(sectionIndex, skillIndex) {
        const roleData = this.taxonomy.target_roles[this.currentTaxonomyRole];
        if (roleData?.sections?.[sectionIndex]?.skills) {
            roleData.sections[sectionIndex].skills.splice(skillIndex, 1);
            this.renderTaxonomySections();
            this.scheduleAutoSave('taxonomy');
        }
    }

    deleteTaxonomySignal(sectionIndex, signalIndex) {
        const roleData = this.taxonomy.target_roles[this.currentTaxonomyRole];
        if (roleData?.sections?.[sectionIndex]?.jd_signals) {
            roleData.sections[sectionIndex].jd_signals.splice(signalIndex, 1);
            this.renderTaxonomySections();
            this.scheduleAutoSave('taxonomy');
        }
    }

    renderSkillAliases() {
        const container = document.getElementById('skill-aliases-container');
        if (!container || !this.taxonomy?.skill_aliases) return;

        // Filter out comment entries - only keep entries where value is an array
        const aliases = Object.entries(this.taxonomy.skill_aliases)
            .filter(([key, value]) => Array.isArray(value));
        if (aliases.length === 0) {
            container.innerHTML = '<div class="text-sm italic p-3" style="color: var(--text-tertiary);">No aliases defined</div>';
            return;
        }

        container.innerHTML = aliases.slice(0, 50).map(([canonical, variations]) => `
            <div class="skill-alias-row">
                <span class="skill-alias-canonical">${this.escapeHtml(canonical)}</span>
                <span class="skill-alias-arrow">→</span>
                <div class="skill-alias-variations">
                    ${variations.map((v, i) => `
                        <span class="master-cv-chip text-xs">
                            ${this.escapeHtml(v)}
                            <button class="chip-delete" onclick="masterCVEditor.deleteAliasVariation('${this.escapeHtml(canonical)}', ${i})" title="Remove">
                                <svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                                </svg>
                            </button>
                        </span>
                    `).join('')}
                    <button onclick="masterCVEditor.showAddAliasVariationModal('${this.escapeHtml(canonical)}')"
                            class="text-xs px-2 py-0.5 rounded-full border border-dashed hover:bg-gray-50"
                            style="border-color: var(--border-default); color: var(--text-tertiary);">
                        + Add
                    </button>
                </div>
            </div>
        `).join('');

        if (aliases.length > 50) {
            container.innerHTML += `<div class="text-xs text-center py-2" style="color: var(--text-tertiary);">Showing 50 of ${aliases.length} aliases</div>`;
        }
    }

    showAddAliasModal() {
        document.getElementById('new-alias-canonical').value = '';
        document.getElementById('new-alias-variations').value = '';
        document.getElementById('add-alias-modal').classList.remove('hidden');
        document.getElementById('new-alias-canonical').focus();
    }

    closeAddAliasModal() {
        document.getElementById('add-alias-modal').classList.add('hidden');
    }

    confirmAddAlias() {
        const canonical = document.getElementById('new-alias-canonical').value.trim().toLowerCase();
        const variations = document.getElementById('new-alias-variations').value
            .split(',')
            .map(v => v.trim())
            .filter(v => v);

        if (!canonical || variations.length === 0) {
            alert('Please enter both a canonical name and at least one variation');
            return;
        }

        if (!this.taxonomy.skill_aliases) {
            this.taxonomy.skill_aliases = {};
        }

        if (this.taxonomy.skill_aliases[canonical]) {
            // Add to existing
            variations.forEach(v => {
                if (!this.taxonomy.skill_aliases[canonical].includes(v)) {
                    this.taxonomy.skill_aliases[canonical].push(v);
                }
            });
        } else {
            this.taxonomy.skill_aliases[canonical] = variations;
        }

        this.renderSkillAliases();
        this.closeAddAliasModal();
        this.scheduleAutoSave('taxonomy');
    }

    showAddAliasVariationModal(canonical) {
        this.addItemType = { type: 'alias-variation', canonical };
        document.getElementById('add-item-title').textContent = `Add Variation for "${canonical}"`;
        document.getElementById('add-item-input').placeholder = 'e.g., K8s, Container Orchestration';
        document.getElementById('add-item-input').value = '';
        document.getElementById('add-item-modal').classList.remove('hidden');
        document.getElementById('add-item-input').focus();
    }

    deleteAliasVariation(canonical, index) {
        if (this.taxonomy.skill_aliases?.[canonical]) {
            this.taxonomy.skill_aliases[canonical].splice(index, 1);
            if (this.taxonomy.skill_aliases[canonical].length === 0) {
                delete this.taxonomy.skill_aliases[canonical];
            }
            this.renderSkillAliases();
            this.scheduleAutoSave('taxonomy');
        }
    }

    updateDefaultFallbackRole(role) {
        this.taxonomy.default_fallback_role = role;
        this.scheduleAutoSave('taxonomy');
    }

    // ==========================================================================
    // SAVE & PERSISTENCE
    // ==========================================================================

    scheduleAutoSave(section) {
        this.pendingChanges[section] = true;
        this.updateSaveIndicator('unsaved');

        if (this.saveTimeout) {
            clearTimeout(this.saveTimeout);
        }

        this.saveTimeout = setTimeout(() => this.save(), this.AUTOSAVE_DELAY);
    }

    async save() {
        if (Object.keys(this.pendingChanges).length === 0) return;

        this.updateSaveIndicator('saving');

        try {
            const savePromises = [];

            // Save metadata (includes candidate and role metadata)
            if (this.pendingChanges['metadata'] || this.pendingChanges['role-metadata']) {
                savePromises.push(
                    fetch('/api/master-cv/metadata', {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            candidate: this.metadata.candidate,
                            roles: this.metadata.roles,
                            change_summary: 'Updated via Master CV Editor'
                        })
                    })
                );
            }

            // Save taxonomy
            if (this.pendingChanges['taxonomy']) {
                savePromises.push(
                    fetch('/api/master-cv/taxonomy', {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            target_roles: this.taxonomy.target_roles,
                            skill_aliases: this.taxonomy.skill_aliases,
                            default_fallback_role: this.taxonomy.default_fallback_role,
                            change_summary: 'Updated via Master CV Editor'
                        })
                    })
                );
            }

            // Save role content
            if (this.pendingChanges['role-content'] && this.currentRoleId) {
                const roleContent = this.roles[this.currentRoleId];
                let markdownContent = '';

                if (this.roleEditor) {
                    // Get content from TipTap
                    markdownContent = this.roleEditor.getHTML();
                } else {
                    // Get from textarea fallback
                    const textarea = document.getElementById('role-markdown-textarea');
                    if (textarea) markdownContent = textarea.value;
                }

                savePromises.push(
                    fetch(`/api/master-cv/roles/${this.currentRoleId}`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            markdown_content: markdownContent,
                            change_summary: 'Updated via Master CV Editor'
                        })
                    })
                );
            }

            await Promise.all(savePromises);
            this.pendingChanges = {};
            this.updateSaveIndicator('saved');

            // Update role markdown indicator
            const indicator = document.getElementById('role-markdown-indicator');
            if (indicator) {
                indicator.textContent = 'Saved';
                indicator.style.color = 'var(--success-600)';
            }

        } catch (error) {
            console.error('Save failed:', error);
            this.updateSaveIndicator('error');
        }
    }

    updateSaveIndicator(status) {
        this.saveStatus = status;
        const icon = document.getElementById('save-status-icon');
        const text = document.getElementById('save-status-text');

        if (!icon || !text) return;

        // Remove all status classes
        icon.className = 'w-2 h-2 rounded-full';

        const statusMap = {
            'loading': { class: 'unsaved', text: 'Loading...' },
            'unsaved': { class: 'unsaved', text: 'Unsaved' },
            'saving': { class: 'saving', text: 'Saving...' },
            'saved': { class: 'saved', text: 'Saved' },
            'error': { class: 'error', text: 'Error' }
        };

        const config = statusMap[status] || statusMap['unsaved'];
        icon.classList.add(config.class);
        text.textContent = config.text;
    }

    // ==========================================================================
    // VERSION HISTORY
    // ==========================================================================

    openVersionHistory() {
        document.getElementById('version-history-modal').classList.remove('hidden');
        this.loadHistory('metadata');
    }

    closeVersionHistory() {
        document.getElementById('version-history-modal').classList.add('hidden');
    }

    async loadHistory(collection) {
        this.currentHistoryCollection = collection;

        // Update tab states
        document.querySelectorAll('.history-tab').forEach(tab => {
            const tabCollection = tab.id.replace('history-tab-', '');
            tab.classList.toggle('active', tabCollection === collection);
        });

        const container = document.getElementById('version-history-list');
        container.innerHTML = `
            <div class="text-center py-8">
                <div class="spinner mx-auto mb-3"></div>
                <p class="text-sm" style="color: var(--text-tertiary);">Loading version history...</p>
            </div>
        `;

        try {
            const res = await fetch(`/api/master-cv/history/${collection}`);
            if (!res.ok) throw new Error('Failed to load history');

            const data = await res.json();
            const history = data.history || [];

            if (history.length === 0) {
                container.innerHTML = `
                    <div class="text-center py-8">
                        <svg class="w-12 h-12 mx-auto mb-3" style="color: var(--text-tertiary);" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/>
                        </svg>
                        <p class="text-sm" style="color: var(--text-tertiary);">No version history available</p>
                    </div>
                `;
                return;
            }

            container.innerHTML = history.map(entry => `
                <div class="history-item">
                    <span class="history-item-version">v${entry.version}</span>
                    <div class="history-item-content">
                        <div class="history-item-meta">
                            ${this.formatDate(entry.timestamp)} · ${entry.updated_by || 'unknown'}
                        </div>
                        <div class="history-item-summary">${this.escapeHtml(entry.change_summary || 'No description')}</div>
                    </div>
                    <button onclick="masterCVEditor.confirmRollback('${collection}', ${entry.version})"
                            class="btn btn-ghost btn-sm">
                        Restore
                    </button>
                </div>
            `).join('');

        } catch (error) {
            console.error('Error loading history:', error);
            container.innerHTML = `
                <div class="text-center py-8">
                    <p class="text-sm text-red-500">Failed to load version history</p>
                </div>
            `;
        }
    }

    confirmRollback(collection, version) {
        this.showDeleteConfirm(
            'Restore Version',
            `Are you sure you want to restore to version ${version}? Your current changes will be saved as a new version.`,
            async () => {
                try {
                    const res = await fetch(`/api/master-cv/rollback/${collection}/${version}`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({})
                    });

                    if (!res.ok) throw new Error('Rollback failed');

                    // Reload data
                    await this.loadAllData();
                    this.closeVersionHistory();
                    this.updateSaveIndicator('saved');

                } catch (error) {
                    console.error('Rollback failed:', error);
                    alert('Failed to restore version. Please try again.');
                }
            }
        );
    }

    // ==========================================================================
    // DELETE CONFIRMATION
    // ==========================================================================

    showDeleteConfirm(title, message, callback) {
        document.getElementById('delete-confirm-title').textContent = title;
        document.getElementById('delete-confirm-message').textContent = message;
        this.deleteCallback = callback;

        // Disable button for 2 seconds
        const btn = document.getElementById('delete-confirm-btn');
        const countdown = document.getElementById('delete-confirm-countdown');
        btn.disabled = true;

        let seconds = 2;
        countdown.textContent = `Delete (${seconds})`;

        const interval = setInterval(() => {
            seconds--;
            if (seconds <= 0) {
                clearInterval(interval);
                btn.disabled = false;
                countdown.textContent = 'Delete';
            } else {
                countdown.textContent = `Delete (${seconds})`;
            }
        }, 1000);

        document.getElementById('delete-confirm-modal').classList.remove('hidden');
    }

    closeDeleteConfirm() {
        document.getElementById('delete-confirm-modal').classList.add('hidden');
        this.deleteCallback = null;
    }

    executeDelete() {
        if (this.deleteCallback) {
            this.deleteCallback();
        }
        this.closeDeleteConfirm();
    }

    // ==========================================================================
    // UTILITIES
    // ==========================================================================

    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    formatDate(isoString) {
        if (!isoString) return 'Unknown date';
        const date = new Date(isoString);
        return date.toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    }

    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Ctrl/Cmd + S to save
            if ((e.ctrlKey || e.metaKey) && e.key === 's') {
                e.preventDefault();
                if (this.saveTimeout) {
                    clearTimeout(this.saveTimeout);
                }
                this.save();
            }
        });
    }
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
    window.masterCVEditor = new MasterCVEditor();
});
