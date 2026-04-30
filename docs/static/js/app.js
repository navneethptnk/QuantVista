// Global state
let currentFile = null;
let currentFilePayload = null;
let savedDashboardItems = [];
const dashboardStorageKey = 'quantvista-dashboards';
const runtimeConfig = window.QUANTVISTA_CONFIG || {};
const apiBaseUrl = normalizeApiBaseUrl(runtimeConfig.apiBaseUrl || '');
const requestMode = resolveRequestMode(runtimeConfig.requestMode);

// DOM Elements
const uploadArea = document.getElementById('uploadArea');
const fileInput = document.getElementById('fileInput');
const fileInfo = document.getElementById('fileInfo');
const fileName = document.getElementById('fileName');
const rowCount = document.getElementById('rowCount');
const columnCount = document.getElementById('columnCount');
const controlsSection = document.getElementById('controlsSection');
const visualizationSection = document.getElementById('visualizationSection');
const analysisSection = document.getElementById('analysisSection');
const loadingOverlay = document.getElementById('loadingOverlay');
const toast = document.getElementById('toast');
const actionStatus = document.getElementById('actionStatus');
const themeToggle = document.getElementById('themeToggle');

// Controls
const chartType = document.getElementById('chartType');
const xColumn = document.getElementById('xColumn');
const yColumn = document.getElementById('yColumn');
const zColumn = document.getElementById('zColumn');
const zColumnGroup = document.getElementById('zColumnGroup');
const colorColumn = document.getElementById('colorColumn');
const chartTitle = document.getElementById('chartTitle');
const aggregation = document.getElementById('aggregation');
const aggregationGroup = document.getElementById('aggregationGroup');
const autoScaleY = document.getElementById('autoScaleY');
const autoScaleGroup = document.getElementById('autoScaleGroup');
const dashboardName = document.getElementById('dashboardName');
const savedDashboards = document.getElementById('savedDashboards');
const dashboardPreview = document.getElementById('dashboardPreview');
const saveDashboardBtn = document.getElementById('saveDashboard');
const loadDashboardBtn = document.getElementById('loadDashboard');
const deleteDashboardBtn = document.getElementById('deleteDashboard');
const exportPngBtn = document.getElementById('exportPng');
const exportSvgBtn = document.getElementById('exportSvg');
const exportHtmlBtn = document.getElementById('exportHtml');
const createVisualizationBtn = document.getElementById('createVisualization');
const analyzeDataBtn = document.getElementById('analyzeData');

// Event Listeners
uploadArea.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', handleFileSelect);
createVisualizationBtn.addEventListener('click', createVisualization);
analyzeDataBtn.addEventListener('click', analyzeData);
chartType.addEventListener('change', handleChartTypeChange);
savedDashboards.addEventListener('change', updateSelectedDashboardPreview);
saveDashboardBtn.addEventListener('click', saveDashboard);
loadDashboardBtn.addEventListener('click', loadDashboard);
deleteDashboardBtn.addEventListener('click', deleteDashboard);
exportPngBtn.addEventListener('click', () => exportChartImage('png'));
exportSvgBtn.addEventListener('click', () => exportChartImage('svg'));
exportHtmlBtn.addEventListener('click', exportChartHtml);
if (themeToggle) {
    themeToggle.addEventListener('change', toggleTheme);
}

initializeTheme();
fetchDashboards();

function normalizeApiBaseUrl(value) {
    const trimmed = String(value || '').trim();
    if (!trimmed) {
        return '';
    }
    return trimmed.replace(/\/+$/, '');
}

function resolveRequestMode(configuredMode) {
    if (configuredMode === 'inline' || configuredMode === 'server') {
        return configuredMode;
    }

    const host = window.location.hostname;
    if (host === 'localhost' || host === '127.0.0.1') {
        return 'server';
    }

    return 'inline';
}

function buildApiUrl(path) {
    return `${apiBaseUrl}${path}`;
}

function loadDashboardsFromStorage() {
    try {
        const stored = localStorage.getItem(dashboardStorageKey);
        const parsed = JSON.parse(stored || '[]');
        return Array.isArray(parsed) ? parsed : [];
    } catch (error) {
        return [];
    }
}

function persistDashboardsToStorage(items) {
    localStorage.setItem(dashboardStorageKey, JSON.stringify(items));
}

function readFileAsBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
            const result = String(reader.result || '');
            const base64Payload = result.includes(',') ? result.split(',')[1] : result;
            resolve(base64Payload);
        };
        reader.onerror = () => reject(reader.error || new Error('Unable to read file'));
        reader.readAsDataURL(file);
    });
}

async function buildInlineFilePayload(file) {
    return {
        original_filename: file.name,
        file_content: await readFileAsBase64(file)
    };
}

function getDataRequestPayload() {
    if (requestMode === 'inline') {
        if (!currentFilePayload) {
            throw new Error('Please upload a file first');
        }
        return { ...currentFilePayload };
    }

    if (!currentFile) {
        throw new Error('Please upload a file first');
    }

    return { filename: currentFile };
}

function setActionStatus(message, type = '') {
    if (!actionStatus) {
        return;
    }
    actionStatus.textContent = message || '';
    actionStatus.className = 'action-status';
    if (type) {
        actionStatus.classList.add(type);
    }
}

function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    try {
        localStorage.setItem('quantvista-theme', theme);
    } catch (e) {}
    if (themeToggle) {
        themeToggle.checked = theme === 'dark';
        themeToggle.setAttribute('aria-label', theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode');
    }
}

function initializeTheme() {
    const attrTheme = document.documentElement.getAttribute('data-theme');
    if (attrTheme === 'dark' || attrTheme === 'light') {
        setTheme(attrTheme);
        return;
    }

    let savedTheme = null;
    try {
        savedTheme = localStorage.getItem('quantvista-theme');
    } catch (e) {}

    if (savedTheme === 'dark' || savedTheme === 'light') {
        setTheme(savedTheme);
        return;
    }

    const systemPrefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    setTheme(systemPrefersDark ? 'dark' : 'light');
}

function toggleTheme() {
    const nextTheme = themeToggle && themeToggle.checked ? 'dark' : 'light';
    setTheme(nextTheme);
}

// Drag and drop functionality
uploadArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadArea.classList.add('drag-over');
});

uploadArea.addEventListener('dragleave', () => {
    uploadArea.classList.remove('drag-over');
});

uploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadArea.classList.remove('drag-over');
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        fileInput.files = files;
        handleFileSelect();
    }
});

// Handle file selection
async function handleFileSelect() {
    const file = fileInput.files[0];
    if (!file) return;

    resetDataViews();

    const formData = new FormData();
    formData.append('file', file);

    showLoading();

    try {
        const response = await fetch(buildApiUrl('/upload'), {
            method: 'POST',
            body: formData
        });
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || `HTTP error! status: ${response.status}`);
        }

        if (data.success) {
            currentFile = data.filename;
            currentFilePayload = await buildInlineFilePayload(file);

            // Update UI - show original filename to user, not UUID version
            fileName.textContent = data.original_filename || data.filename;
            rowCount.textContent = data.row_count.toLocaleString();
            columnCount.textContent = data.column_count;

            fileInfo.style.display = 'block';
            controlsSection.style.display = 'block';

            // Populate column dropdowns
            populateColumnSelects(data.columns);

            // Initialize chart type hints
            handleChartTypeChange();

            // Smooth scroll to controls
            controlsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });

            showToast('File uploaded successfully!', 'success');
            setActionStatus('File uploaded. Configure chart settings and create a visualization.', 'success');
        } else {
            showToast(data.error || 'Upload failed', 'error');
            setActionStatus(data.error || 'Upload failed', 'error');
        }
    } catch (error) {
        showToast('Error uploading file: ' + error.message, 'error');
        setActionStatus('Error uploading file: ' + error.message, 'error');
    } finally {
        hideLoading();
    }
}

function resetDataViews() {
    analysisSection.style.display = 'none';
    visualizationSection.style.display = 'none';
    const analysisContent = document.getElementById('analysisContent');
    const plotDiv = document.getElementById('plotDiv');

    if (analysisContent) {
        analysisContent.innerHTML = '';
    }

    if (plotDiv) {
        try {
            Plotly.purge(plotDiv);
        } catch (e) {}
        plotDiv.innerHTML = '';
    }
}

// Populate column select dropdowns
function populateColumnSelects(columns) {
    // Clear existing options
    xColumn.innerHTML = '<option value="">Select column...</option>';
    yColumn.innerHTML = '<option value="">Select column...</option>';
    zColumn.innerHTML = '<option value="">Select column...</option>';
    colorColumn.innerHTML = '<option value="">None</option>';

    columns.forEach(col => {
        const xOption = new Option(col.name, col.name);
        const yOption = new Option(col.name, col.name);
        const zOption = new Option(col.name, col.name);
        const colorOption = new Option(col.name, col.name);

        xColumn.appendChild(xOption);
        yColumn.appendChild(yOption);
        zColumn.appendChild(zOption);
        colorColumn.appendChild(colorOption);
    });
}

// Handle chart type change
function handleChartTypeChange() {
    const selectedType = chartType.value;
    
    // Define requirements for each chart type
    const chartRequirements = {
        'bar': { x: true, y: true, z: false, color: true },
        'line': { x: true, y: true, z: false, color: true },
        'area': { x: true, y: true, z: false, color: true },
        'scatter': { x: true, y: true, z: false, color: true },
        'bubble': { x: true, y: true, z: true, color: true },
        'pie': { x: true, y: false, z: false, color: false },
        'histogram': { x: true, y: false, z: false, color: true },
        'box': { x: false, y: true, z: false, color: true },
        'violin': { x: true, y: true, z: false, color: true },
        'heatmap': { x: true, y: true, z: false, color: false },
        'sunburst': { x: true, y: false, z: false, color: true },
        'treemap': { x: true, y: false, z: false, color: false }
    };
    
    const requirements = chartRequirements[selectedType] || { x: true, y: true, z: false, color: true };

    // Show/hide Z column based on chart type
    zColumnGroup.style.display = requirements.z ? 'block' : 'none';

    // Show aggregation for charts that group data
    const aggregationCharts = ['bar', 'pie', 'treemap', 'sunburst'];
    aggregationGroup.style.display = aggregationCharts.includes(selectedType) ? 'block' : 'none';

    // Show auto-scale toggle only for charts with Y-axis values where this is meaningful
    const autoScaleCharts = ['bar', 'line', 'scatter', 'box', 'area', 'bubble', 'violin'];
    autoScaleGroup.style.display = autoScaleCharts.includes(selectedType) ? 'block' : 'none';

    // Update labels and required indicators
    updateControlVisibility('xColumn', requirements.x, 'X-Axis');
    updateControlVisibility('yColumn', requirements.y, 'Y-Axis');
    updateControlVisibility('colorColumn', requirements.color, 'Color By');
    
    // Add helpful hints
    updateChartHint(selectedType);
}

// Update control visibility and labels
function updateControlVisibility(controlId, isRequired, labelText) {
    const control = document.getElementById(controlId);
    const controlGroup = control.closest('.control-group');
    const label = controlGroup.querySelector('.control-label');
    
    if (isRequired) {
        controlGroup.style.display = 'block';
        label.innerHTML = `${labelText} ${isRequired ? '<span style="color: #ef4444;">*</span>' : ''}`;
    } else {
        controlGroup.style.display = 'none';
    }
}

// Add hint for each chart type
function updateChartHint(chartType) {
    const hints = {
        'bar': 'Best for comparing values across categories',
        'line': 'Best for showing trends over time or continuous data',
        'area': 'Best for showing cumulative totals over time',
        'scatter': 'Best for showing relationships between two variables',
        'bubble': 'Like scatter plot but bubble size represents a third variable (requires X, Y, and Z)',
        'pie': 'Best for showing proportions (requires X, Y is optional)',
        'histogram': 'Best for showing distribution of a single variable',
        'box': 'Best for comparing distributions across categories',
        'violin': 'Best for comparing distributions with density curves',
        'heatmap': 'Shows relationships between three variables (Z is optional for Correlation matrices)',
        'sunburst': 'Best for hierarchical data visualization (use X and optionally Color)',
        'treemap': 'Best for hierarchical proportions (use X and optionally Y for values)'
    };
    
    // Remove existing hint if any
    const existingHint = document.getElementById('chartHint');
    if (existingHint) {
        existingHint.remove();
    }
    
    // Add new hint
    const hint = document.createElement('div');
    hint.id = 'chartHint';
    hint.className = 'chart-hint';
    hint.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width: 16px; height: 16px; display: inline-block; margin-right: 6px;">
        <circle cx="12" cy="12" r="10"></circle>
        <path d="M12 16v-4"></path>
        <path d="M12 8h.01"></path>
    </svg>${hints[chartType] || 'Select columns to visualize your data'}`;
    
    const controlGrid = document.querySelector('.basic-grid');
    controlGrid.parentNode.insertBefore(hint, controlGrid);
}

function isSmallScreen() {
    return window.matchMedia('(max-width: 768px)').matches;
}

function getResponsivePlotLayout(baseLayout) {
    if (!isSmallScreen()) {
        return baseLayout;
    }

    return {
        ...baseLayout,
        margin: {
            l: 42,
            r: 12,
            t: 64,
            b: 54
        },
        height: Math.min(Math.max(window.innerHeight * 0.56, 300), 440)
    };
}

function getCurrentChartConfig() {
    return {
        chart_type: chartType.value,
        x_column: xColumn.value,
        y_column: yColumn.value,
        z_column: zColumn.value,
        color_column: colorColumn.value,
        aggregation: aggregation ? aggregation.value : 'sum',
        auto_scale: autoScaleY ? autoScaleY.checked : true,
        title: chartTitle.value || 'Data Visualization'
    };
}

function applyChartConfig(config) {
    if (!config) {
        return;
    }

    chartType.value = config.chart_type || chartType.value;
    handleChartTypeChange();

    xColumn.value = config.x_column || '';
    yColumn.value = config.y_column || '';
    zColumn.value = config.z_column || '';
    colorColumn.value = config.color_column || '';
    if (aggregation) {
        aggregation.value = config.aggregation || 'sum';
    }
    if (autoScaleY) {
        autoScaleY.checked = config.auto_scale !== false;
    }
    chartTitle.value = config.title || 'Data Visualization';
}

function describeDashboardConfig(config) {
    if (!config) {
        return 'No configuration available.';
    }
    const xVal = config.x_column || 'N/A';
    const yVal = config.y_column || 'N/A';
    const chartVal = config.chart_type || 'N/A';
    const aggVal = config.aggregation || 'sum';
    const scaleVal = config.auto_scale === false ? 'Standard axis' : 'Auto-scale';
    return `Chart: ${chartVal} | X: ${xVal} | Y: ${yVal} | Aggregation: ${aggVal} | Scale: ${scaleVal}`;
}

function updateSelectedDashboardPreview() {
    if (!dashboardPreview) {
        return;
    }

    const selected = getSelectedDashboard();
    if (!selected) {
        dashboardPreview.textContent = 'Select a saved dashboard to preview its configuration.';
        return;
    }

    const dateText = selected.created_at ? new Date(selected.created_at).toLocaleString() : 'Unknown date';
    dashboardPreview.textContent = `${selected.name} - ${describeDashboardConfig(selected.config)} - Saved: ${dateText}`;
}

function populateSavedDashboards() {
    savedDashboards.innerHTML = '';

    if (!savedDashboardItems.length) {
        savedDashboards.appendChild(new Option('No saved dashboards', ''));
        updateSelectedDashboardPreview();
        return;
    }

    savedDashboards.appendChild(new Option('Select dashboard...', ''));
    savedDashboardItems.forEach(item => {
        const label = `${item.name} (${new Date(item.created_at).toLocaleDateString()})`;
        savedDashboards.appendChild(new Option(label, item.id));
    });
    updateSelectedDashboardPreview();
}

async function fetchDashboards() {
    try {
        savedDashboardItems = loadDashboardsFromStorage().sort((a, b) => {
            const dateA = String(a && a.created_at ? a.created_at : '');
            const dateB = String(b && b.created_at ? b.created_at : '');
            return dateB.localeCompare(dateA);
        });
        populateSavedDashboards();
        setActionStatus(`Loaded ${savedDashboardItems.length} saved dashboard(s).`);
    } catch (error) {
        showToast(`Error loading dashboards: ${error.message}`, 'error');
        setActionStatus(`Error loading dashboards: ${error.message}`, 'error');
    }
}

async function saveDashboard() {
    const name = dashboardName.value.trim();
    if (!name) {
        showToast('Please enter a dashboard name', 'warning');
        setActionStatus('Please enter a dashboard name before saving.', 'warning');
        return;
    }

    const payload = {
        id: `dashboard_${Date.now()}`,
        name,
        config: getCurrentChartConfig()
    };

    try {
        const dashboard = {
            ...payload,
            created_at: new Date().toISOString()
        };
        const nextDashboards = loadDashboardsFromStorage()
            .filter(item => item && item.id !== dashboard.id)
            .slice(0, 99);
        nextDashboards.unshift(dashboard);
        persistDashboardsToStorage(nextDashboards);
        dashboardName.value = '';
        await fetchDashboards();
        savedDashboards.value = dashboard.id;
        updateSelectedDashboardPreview();
        showToast('Dashboard saved', 'success');
        setActionStatus(`Dashboard "${dashboard.name}" saved.`, 'success');
    } catch (error) {
        showToast(`Error saving dashboard: ${error.message}`, 'error');
        setActionStatus(`Error saving dashboard: ${error.message}`, 'error');
    }
}

function getSelectedDashboard() {
    const selectedId = savedDashboards.value;
    if (!selectedId) {
        return null;
    }
    return savedDashboardItems.find(item => item.id === selectedId) || null;
}

function loadDashboard() {
    const selected = getSelectedDashboard();
    if (!selected) {
        showToast('Please select a dashboard to load', 'warning');
        setActionStatus('Select a dashboard to load.', 'warning');
        return;
    }

    applyChartConfig(selected.config);
    updateSelectedDashboardPreview();
    showToast(`Loaded "${selected.name}"`, 'success');
    setActionStatus(`Loaded dashboard "${selected.name}".`, 'success');
}

async function deleteDashboard() {
    const selected = getSelectedDashboard();
    if (!selected) {
        showToast('Please select a dashboard to delete', 'warning');
        setActionStatus('Select a dashboard to delete.', 'warning');
        return;
    }

    try {
        const nextDashboards = loadDashboardsFromStorage().filter(item => item && item.id !== selected.id);
        persistDashboardsToStorage(nextDashboards);
        await fetchDashboards();
        showToast(`Deleted "${selected.name}"`, 'success');
        setActionStatus(`Deleted dashboard "${selected.name}".`, 'success');
    } catch (error) {
        showToast(`Error deleting dashboard: ${error.message}`, 'error');
        setActionStatus(`Error deleting dashboard: ${error.message}`, 'error');
    }
}

async function exportChartImage(format) {
    const plotDiv = document.getElementById('plotDiv');
    if (!plotDiv || !plotDiv.data || !plotDiv.layout) {
        showToast('Create a visualization before exporting', 'warning');
        setActionStatus('Create a visualization before exporting.', 'warning');
        return;
    }

    const safeTitle = (chartTitle.value || 'chart').replace(/[^a-z0-9-_]+/gi, '_').toLowerCase();
    try {
        await Plotly.downloadImage(plotDiv, {
            format,
            filename: safeTitle,
            width: 1400,
            height: 900,
            scale: 2
        });
        showToast(`Exported ${format.toUpperCase()} successfully`, 'success');
        setActionStatus(`Exported chart as ${format.toUpperCase()}.`, 'success');
    } catch (error) {
        showToast(`Export failed: ${error.message}`, 'error');
        setActionStatus(`Export failed: ${error.message}`, 'error');
    }
}

function exportChartHtml() {
    const plotDiv = document.getElementById('plotDiv');
    if (!plotDiv || !plotDiv.data || !plotDiv.layout) {
        showToast('Create a visualization before exporting', 'warning');
        setActionStatus('Create a visualization before exporting.', 'warning');
        return;
    }

    const safeTitle = (chartTitle.value || 'chart').replace(/[^a-z0-9-_]+/gi, '_').toLowerCase();
    const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${safeTitle}</title>
  <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
</head>
<body style="margin:0;padding:0;background:#fff;">
  <div id="plot" style="width:100vw;height:100vh;"></div>
  <script>
    const data = ${JSON.stringify(plotDiv.data)};
    const layout = ${JSON.stringify(plotDiv.layout)};
    Plotly.newPlot('plot', data, layout, {responsive: true, displaylogo: false});
  </script>
</body>
</html>`;

    const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${safeTitle}.html`;
    a.click();
    URL.revokeObjectURL(url);
    showToast('Exported HTML successfully', 'success');
    setActionStatus('Exported chart as HTML.', 'success');
}

// Create visualization
async function createVisualization() {
    if (!currentFile) {
        showToast('Please upload a file first', 'warning');
        setActionStatus('Upload a file before creating a visualization.', 'warning');
        return;
    }

    const currentConfig = getCurrentChartConfig();
    const selectedChartType = currentConfig.chart_type;
    const selectedX = currentConfig.x_column;
    const selectedY = currentConfig.y_column;
    const selectedZ = currentConfig.z_column;
    const selectedColor = currentConfig.color_column;
    const selectedAggregation = currentConfig.aggregation;
    const autoScaleEnabled = currentConfig.auto_scale;
    const title = currentConfig.title;

    // Chart-specific validation
    const validationRules = {
        'bar': () => {
            if (!selectedX) {
                showToast('Please select an X-axis column for bar chart', 'warning');
                return false;
            }
            return true;
        },
        'heatmap': () => {
            if (!selectedX || !selectedY) {
                showToast('Please select X and Y columns for heatmap', 'warning');
                return false;
            }
            return true;
        },
        'histogram': () => {
            if (!selectedX) {
                showToast('Please select X-axis column for histogram', 'warning');
                return false;
            }
            return true;
        },
        'pie': () => {
            if (!selectedX) {
                showToast('Please select at least X categorical column for pie chart', 'warning');
                return false;
            }
            return true;
        },
        'bubble': () => {
            if (!selectedX || !selectedY || !selectedZ) {
                showToast('Please select X, Y, and Z columns for bubble chart', 'warning');
                return false;
            }
            return true;
        },
        'box': () => {
            if (!selectedY) {
                showToast('Please select a Y-axis column for box plot', 'warning');
                return false;
            }
            return true;
        },
        'sunburst': () => {
            if (!selectedX) {
                showToast('Please select X-axis column for sunburst chart', 'warning');
                return false;
            }
            return true;
        },
        'treemap': () => {
            if (!selectedX) {
                showToast('Please select X-axis column for treemap', 'warning');
                return false;
            }
            return true;
        },
        'default': () => {
            if (!selectedX || !selectedY) {
                showToast('Please select both X and Y columns', 'warning');
                return false;
            }
            return true;
        }
    };

    // Run validation
    const validator = validationRules[selectedChartType] || validationRules['default'];
    if (!validator()) {
        return;
    }

    showLoading();

    const requestData = {
        ...getDataRequestPayload(),
        chart_type: selectedChartType,
        x_column: selectedX,
        y_column: selectedY,
        z_column: selectedZ,
        color_column: selectedColor,
        aggregation: selectedAggregation,
        auto_scale: autoScaleEnabled,
        title: title
    };

    try {
        const response = await fetch(buildApiUrl('/visualize'), {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestData)
        });
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || `HTTP error! status: ${response.status}`);
        }

        if (data.success) {
            const graphData = JSON.parse(data.graph);
            const plotDiv = document.getElementById('plotDiv');

            // Clear any existing plot
            try {
                Plotly.purge(plotDiv);
            } catch (e) {}

            const layout = getResponsivePlotLayout(graphData.layout || {});
            const mobileModeBarButtons = ['pan2d', 'lasso2d', 'select2d', 'autoScale2d'];
            const desktopModeBarButtons = ['pan2d', 'lasso2d', 'select2d'];

            // Create the plot with responsive configuration
            Plotly.newPlot(plotDiv, graphData.data, layout, {
                responsive: true,
                displayModeBar: !isSmallScreen(),
                displaylogo: false,
                modeBarButtonsToRemove: isSmallScreen() ? mobileModeBarButtons : desktopModeBarButtons
            }).catch(err => {
                console.error('Error creating plot:', err);
                showToast('Failed to render visualization', 'error');
            });

            // Show the visualization section
            visualizationSection.style.display = 'block';

            // Force a resize after showing
            window.setTimeout(() => {
                Plotly.Plots.resize(plotDiv);
                visualizationSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }, 150);

            showToast('Visualization created successfully!', 'success');
            setActionStatus('Visualization created successfully.', 'success');
        } else {
            showToast(data.error || 'Visualization failed', 'error');
            setActionStatus(data.error || 'Visualization failed', 'error');
        }
    } catch (error) {
        showToast('Error creating visualization: ' + error.message, 'error');
        setActionStatus('Error creating visualization: ' + error.message, 'error');
    } finally {
        hideLoading();
    }
}

// Analyze data
async function analyzeData() {
    if (!currentFile) {
        showToast('Please upload a file first', 'warning');
        setActionStatus('Upload a file before analysis.', 'warning');
        return;
    }

    showLoading();

    try {
        const response = await fetch(buildApiUrl('/analyze'), {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(getDataRequestPayload())
        });
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || `HTTP error! status: ${response.status}`);
        }

        if (data.success) {
            displayAnalysis(data.analysis);
            analysisSection.style.display = 'block';
            analysisSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
            showToast('Analysis completed!', 'success');
            setActionStatus('Analysis completed successfully.', 'success');
        } else {
            showToast(data.error || 'Analysis failed', 'error');
            setActionStatus(data.error || 'Analysis failed', 'error');
        }
    } catch (error) {
        showToast('Error analyzing data: ' + error.message, 'error');
        setActionStatus('Error analyzing data: ' + error.message, 'error');
    } finally {
        hideLoading();
    }
}

// Helper function to escape HTML and prevent XSS
function escapeHtml(text) {
    if (text === null || text === undefined) {
        return '';
    }
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

// Display analysis results
function displayAnalysis(analysis) {
    const analysisContent = document.getElementById('analysisContent');
    let html = '';

    // Basic statistics
    if (analysis.basic_stats && Object.keys(analysis.basic_stats).length > 0) {
        html += '<div class="analysis-card"><h3>Statistical Summary</h3><div class="stats-grid">';

        for (const [column, stats] of Object.entries(analysis.basic_stats)) {
            html += `
                <div class="stat-item">
                    <div style="font-weight: 600; margin-bottom: 0.5rem; color: var(--primary-color);">${escapeHtml(column)}</div>
                    <div style="font-size: 0.85rem; color: var(--text-secondary);">
                        <div>Mean: <strong>${stats.mean !== null ? stats.mean.toFixed(2) : 'N/A'}</strong></div>
                        <div>Median: <strong>${stats.median !== null ? stats.median.toFixed(2) : 'N/A'}</strong></div>
                        <div>Std: <strong>${stats.std !== null ? stats.std.toFixed(2) : 'N/A'}</strong></div>
                        <div>Min: <strong>${stats.min !== null ? stats.min.toFixed(2) : 'N/A'}</strong></div>
                        <div>Max: <strong>${stats.max !== null ? stats.max.toFixed(2) : 'N/A'}</strong></div>
                    </div>
                </div>
            `;
        }

        html += '</div></div>';
    }

    // Correlations
    if (analysis.correlations && analysis.correlations.pairs && analysis.correlations.pairs.length > 0) {
        html += '<div class="analysis-card"><h3>Strong Correlations</h3>';
        html += '<div style="overflow-x: auto;"><table style="width: 100%; border-collapse: collapse;">';
        html += '<thead><tr style="background: var(--bg-color);"><th style="padding: 0.75rem; text-align: left;">Variable 1</th><th style="padding: 0.75rem; text-align: left;">Variable 2</th><th style="padding: 0.75rem; text-align: right;">Correlation</th></tr></thead><tbody>';

        analysis.correlations.pairs.slice(0, 10).forEach(pair => {
            const corrClass = pair.correlation > 0 ? 'success-color' : 'error-color';
            html += `
                <tr style="border-bottom: 1px solid var(--border-color);">
                    <td style="padding: 0.75rem;">${escapeHtml(pair.var1)}</td>
                    <td style="padding: 0.75rem;">${escapeHtml(pair.var2)}</td>
                    <td style="padding: 0.75rem; text-align: right; font-weight: 600; color: var(--${corrClass});">${pair.correlation.toFixed(3)}</td>
                </tr>
            `;
        });

        html += '</tbody></table></div></div>';
    }

    // Categorical analysis
    if (analysis.categorical_analysis && Object.keys(analysis.categorical_analysis).length > 0) {
        html += '<div class="analysis-card"><h3>Categorical Data Summary</h3>';

        for (const [column, catData] of Object.entries(analysis.categorical_analysis)) {
            html += `<div style="margin-bottom: 1.5rem;">`;
            html += `<h4 style="color: var(--primary-color); margin-bottom: 0.5rem;">${escapeHtml(column)}</h4>`;
            html += `<p style="color: var(--text-secondary); margin-bottom: 0.5rem;">Unique values: <strong>${catData.unique_values}</strong></p>`;

            if (catData.top_values) {
                html += '<div style="font-size: 0.9rem;">';
                html += '<strong>Top values:</strong>';
                html += '<ul style="margin-top: 0.5rem; padding-left: 1.5rem;">';

                for (const [value, count] of Object.entries(catData.top_values)) {
                    html += `<li>${escapeHtml(value)}: <strong>${count}</strong></li>`;
                }

                html += '</ul></div>';
            }

            html += '</div>';
        }

        html += '</div>';
    }

    analysisContent.innerHTML = html || '<p>No analysis data available.</p>';
}

// Utility functions
function showLoading() {
    loadingOverlay.style.display = 'flex';
}

function hideLoading() {
    loadingOverlay.style.display = 'none';
}

function showToast(message, type = 'success') {
    toast.textContent = message;
    toast.className = `toast ${type} show`;

    setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

// Handle window resize for responsive charts
let resizeTimeout;
window.addEventListener('resize', () => {
    clearTimeout(resizeTimeout);
    resizeTimeout = setTimeout(() => {
        const plotDiv = document.getElementById('plotDiv');
        if (plotDiv && plotDiv.data) {
            if (isSmallScreen()) {
                Plotly.relayout(plotDiv, {
                    height: Math.min(Math.max(window.innerHeight * 0.56, 300), 440)
                });
            }
            Plotly.Plots.resize(plotDiv);
        }
    }, 200);
});
