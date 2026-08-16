/**
 * klipper-tui Modern Landing Page Interactive Scripts
 */

document.addEventListener('DOMContentLoaded', () => {
  initThemeSystem();
  initTuiTabs();
  initCopyButtons();
  initConsoleSimulator();
  init3DWireframe();
  initBrailleGraph();
  initBedMesh();
  initToolpathViewer();
  initWebcamSimulator();
  initShortcutsFilter();
  initLiveClock();
  initLightbox();
});

/* --------------------------------------------------------------------------
   1. Theme System
   -------------------------------------------------------------------------- */
const THEMES = ['ominous', 'mainsail', 'forge'];
let currentThemeIndex = 0;

function initThemeSystem() {
  const html = document.documentElement;
  const themeDropdownBtn = document.getElementById('themeDropdownBtn');
  const themeDropdownMenu = document.getElementById('themeDropdownMenu');
  const currentThemeLabel = document.getElementById('currentThemeLabel');
  const themeOptions = document.querySelectorAll('.theme-option');
  const radioInputs = document.querySelectorAll('input[name="appTheme"]');

  function applyTheme(themeName) {
    if (!THEMES.includes(themeName)) themeName = 'ominous';
    html.setAttribute('data-theme', themeName);
    currentThemeIndex = THEMES.indexOf(themeName);

    // Update label
    const formatted = themeName.charAt(0).toUpperCase() + themeName.slice(1);
    if (currentThemeLabel) currentThemeLabel.textContent = formatted;

    // Update dropdown options active state
    themeOptions.forEach(opt => {
      opt.classList.toggle('active', opt.dataset.themeVal === themeName);
    });

    // Update settings radio buttons
    radioInputs.forEach(r => {
      r.checked = (r.value === themeName);
    });

    // Redraw 3D canvas with new theme colors if active
    if (window.redraw3D) window.redraw3D();
  }

  // Toggle Dropdown
  if (themeDropdownBtn && themeDropdownMenu) {
    themeDropdownBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      themeDropdownMenu.classList.toggle('show');
      themeDropdownBtn.classList.toggle('open');
    });

    document.addEventListener('click', () => {
      themeDropdownMenu.classList.remove('show');
      themeDropdownBtn.classList.remove('open');
    });

    themeOptions.forEach(opt => {
      opt.addEventListener('click', () => {
        const selected = opt.dataset.themeVal;
        applyTheme(selected);
        themeDropdownMenu.classList.remove('show');
        themeDropdownBtn.classList.remove('open');
      });
    });
  }

  // Settings Radio change
  radioInputs.forEach(r => {
    r.addEventListener('change', (e) => {
      applyTheme(e.target.value);
    });
  });

  // Cycle theme with key 't'
  window.cycleTheme = () => {
    currentThemeIndex = (currentThemeIndex + 1) % THEMES.length;
    applyTheme(THEMES[currentThemeIndex]);
  };
}

/* --------------------------------------------------------------------------
   2. TUI Tab Navigation System
   -------------------------------------------------------------------------- */
function initTuiTabs() {
  const tabButtons = document.querySelectorAll('.tui-tab');
  const viewPanels = document.querySelectorAll('.tui-view-panel');

  const tabKeyMap = {
    'd': 'dashboard',
    'c': 'console',
    'm': 'move',
    'f': 'files',
    'b': 'mesh',
    'w': 'webcam',
    'g': 'graph',
    's': 'settings'
  };

  function switchTab(tabId) {
    tabButtons.forEach(btn => {
      const isTarget = btn.dataset.tab === tabId;
      btn.classList.toggle('active', isTarget);
      btn.setAttribute('aria-selected', isTarget);
    });

    viewPanels.forEach(panel => {
      const panelId = 'view' + tabId.charAt(0).toUpperCase() + tabId.slice(1);
      panel.classList.toggle('active', panel.id === panelId);
    });
  }

  tabButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      switchTab(btn.dataset.tab);
    });
  });

  // Global Keyboard Navigation (when not focused in inputs)
  document.addEventListener('keydown', (e) => {
    const activeEl = document.activeElement;
    const isInput = activeEl && (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA');

    if (!isInput) {
      const key = e.key.toLowerCase();
      if (tabKeyMap[key]) {
        e.preventDefault();
        switchTab(tabKeyMap[key]);
      } else if (key === 't') {
        e.preventDefault();
        if (window.cycleTheme) window.cycleTheme();
      }
    }
  });

  // Mobile menu toggle
  const mobileToggle = document.getElementById('mobileToggle');
  const navLinks = document.getElementById('navLinks');
  if (mobileToggle && navLinks) {
    mobileToggle.addEventListener('click', () => {
      navLinks.classList.toggle('show');
    });
  }
}

/* --------------------------------------------------------------------------
   3. Copy Buttons & Snippets
   -------------------------------------------------------------------------- */
function initCopyButtons() {
  // Hero install tab switcher
  const installTabs = document.querySelectorAll('.install-tab-btn');
  const heroInstallCmd = document.getElementById('heroInstallCmd');

  installTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      installTabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      if (heroInstallCmd) {
        heroInstallCmd.textContent = tab.dataset.cmd;
      }
    });
  });

  // Hero copy button
  const heroCopyBtn = document.getElementById('heroCopyBtn');
  if (heroCopyBtn && heroInstallCmd) {
    heroCopyBtn.addEventListener('click', () => {
      navigator.clipboard.writeText(heroInstallCmd.textContent).then(() => {
        heroCopyBtn.classList.add('copied');
        const tooltip = heroCopyBtn.querySelector('.copy-tooltip');
        if (tooltip) tooltip.textContent = 'Copied!';
        setTimeout(() => {
          heroCopyBtn.classList.remove('copied');
          if (tooltip) tooltip.textContent = 'Copy';
        }, 2000);
      });
    });
  }

  // Generic snippet copy buttons
  document.querySelectorAll('.copy-snippet-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const textToCopy = btn.getAttribute('data-copy');
      if (textToCopy) {
        navigator.clipboard.writeText(textToCopy).then(() => {
          const original = btn.textContent;
          btn.textContent = 'Copied!';
          setTimeout(() => {
            btn.textContent = original;
          }, 2000);
        });
      }
    });
  });
}

/* --------------------------------------------------------------------------
   4. Interactive G-Code Console Simulator
   -------------------------------------------------------------------------- */
function initConsoleSimulator() {
  const form = document.getElementById('consoleForm');
  const input = document.getElementById('consoleInput');
  const output = document.getElementById('consoleOutput');
  const history = [];
  let historyIdx = -1;

  if (!form || !input || !output) return;

  function appendLog(text, className = '') {
    const line = document.createElement('div');
    line.className = `log-line ${className}`;
    line.textContent = text;
    output.appendChild(line);
    output.scrollTop = output.scrollHeight;
  }

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const cmd = input.value.trim();
    if (!cmd) return;

    appendLog(`> ${cmd}`, 'log-cmd');
    history.push(cmd);
    historyIdx = history.length;
    input.value = '';

    // Handle commands
    const upper = cmd.toUpperCase();
    setTimeout(() => {
      if (upper === 'CLEAR' || upper === 'CLS') {
        output.innerHTML = '';
        appendLog('Console cleared.', 'log-system');
      } else if (upper === 'M105') {
        appendLog('ok B:60.2 /60.0 T0:215.0 /215.0', 'log-response');
      } else if (upper.startsWith('M104') || upper.startsWith('M109')) {
        appendLog('// Target temperature set for extruder.', 'log-success');
        appendLog('ok', 'log-response');
      } else if (upper.startsWith('M140') || upper.startsWith('M190')) {
        appendLog('// Target temperature set for heater_bed.', 'log-success');
        appendLog('ok', 'log-response');
      } else if (upper === 'G28' || upper.startsWith('G28')) {
        appendLog('// Homing XYZ axes...', 'log-dim');
        setTimeout(() => {
          appendLog('// Homing completed successfully.', 'log-success');
          appendLog('ok', 'log-response');
        }, 400);
      } else if (upper === 'BED_MESH_CALIBRATE') {
        appendLog('// Bed mesh probe started (5x5 grid)...', 'log-dim');
        appendLog('// Probe at 30.00, 30.00 is z=0.012', 'log-system');
        appendLog('// Probe at 90.00, 30.00 is z=0.005', 'log-system');
        appendLog('// Mesh calibration complete. Use SAVE_CONFIG to persist.', 'log-success');
        appendLog('ok', 'log-response');
      } else if (upper === 'STATUS' || upper === 'GET_POSITION') {
        appendLog('// toolhead: X:174.250 Y:148.800 Z:40.800 E:1248.600', 'log-response');
        appendLog('// print_stats: state=printing, filename=benchy_highspeed_pla.gcode, progress=68%', 'log-response');
        appendLog('ok', 'log-response');
      } else if (upper === 'HELP') {
        appendLog('Available demo commands:', 'log-system');
        appendLog('  G28                 - Home all axes', 'log-dim');
        appendLog('  M105                - Report temperatures', 'log-dim');
        appendLog('  M104 S220           - Set hotend temperature', 'log-dim');
        appendLog('  M140 S60            - Set bed temperature', 'log-dim');
        appendLog('  BED_MESH_CALIBRATE  - Perform bed leveling', 'log-dim');
        appendLog('  STATUS              - Query printer state', 'log-dim');
        appendLog('  CLEAR               - Clear console output', 'log-dim');
        appendLog('ok', 'log-response');
      } else {
        appendLog(`// Send gcode: ${cmd}`, 'log-dim');
        appendLog('ok', 'log-response');
      }
    }, 80);
  });

  // History recall with arrow keys
  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowUp') {
      if (history.length > 0 && historyIdx > 0) {
        historyIdx--;
        input.value = history[historyIdx];
      }
    } else if (e.key === 'ArrowDown') {
      if (historyIdx < history.length - 1) {
        historyIdx++;
        input.value = history[historyIdx];
      } else {
        historyIdx = history.length;
        input.value = '';
      }
    }
  });
}

/* --------------------------------------------------------------------------
   5. 3D Isometric Build Volume Visualizer Engine
   -------------------------------------------------------------------------- */
function init3DWireframe() {
  const canvas = document.getElementById('wireframeCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  let yaw = 0.75;
  let tilt = 0.55;
  let autoSpin = true;
  let toolhead = { x: 174.2, y: 148.8, z: 40.8 };
  const bounds = { x: 300, y: 300, z: 300 };

  const corners = [
    [-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1], // bottom floor
    [-1, -1,  1], [1, -1,  1], [1, 1,  1], [-1, 1,  1], // top ceiling
  ];

  const edges = [
    [0, 1], [1, 2], [2, 3], [3, 0], // floor
    [4, 5], [5, 6], [6, 7], [7, 4], // ceiling
    [0, 4], [1, 5], [2, 6], [3, 7], // verticals
  ];

  function project(x, y, z, width, height, scale = 95) {
    // Rotate Yaw (around Z)
    const cosY = Math.cos(yaw);
    const sinY = Math.sin(yaw);
    const x1 = x * cosY - y * sinY;
    const y1 = x * sinY + y * cosY;
    const z1 = z;

    // Rotate Tilt (around X). z2 was previously written in terms of itself,
    // which threw on every load and took the rest of the demo's start-up down
    // with it — the bed mesh, the braille graph, the webcam and the clock all
    // initialise after this one.
    const cosT = Math.cos(tilt);
    const sinT = Math.sin(tilt);
    const z2 = y1 * sinT + z1 * cosT; // isometric elevation

    const px = width / 2 + x1 * scale;
    const py = height / 2 - z2 * scale;
    return [px, py];
  }

  function getThemeColors() {
    const style = getComputedStyle(document.documentElement);
    return {
      frame: style.getPropertyValue('--border-active').trim() || '#a32638',
      floor: style.getPropertyValue('--border-subtle').trim() || '#3a3325',
      head: '#e0a13c',
      drop: style.getPropertyValue('--accent').trim() || '#c4485a',
      accent: style.getPropertyValue('--primary').trim() || '#a32638',
    };
  }

  function render() {
    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);
    const colors = getThemeColors();

    if (autoSpin) {
      yaw += 0.012;
    }

    // 1. Draw floor grid
    ctx.strokeStyle = colors.floor;
    ctx.lineWidth = 1;
    for (let i = -1; i <= 1; i += 0.5) {
      const p1 = project(i, -1, -1, w, h);
      const p2 = project(i, 1, -1, w, h);
      ctx.beginPath();
      ctx.moveTo(p1[0], p1[1]);
      ctx.lineTo(p2[0], p2[1]);
      ctx.stroke();

      const p3 = project(-1, i, -1, w, h);
      const p4 = project(1, i, -1, w, h);
      ctx.beginPath();
      ctx.moveTo(p3[0], p3[1]);
      ctx.lineTo(p4[0], p4[1]);
      ctx.stroke();
    }

    // 2. Draw wireframe cube bounding box
    ctx.strokeStyle = colors.frame;
    ctx.lineWidth = 1.5;
    edges.forEach(([i, j]) => {
      const p1 = project(corners[i][0], corners[i][1], corners[i][2], w, h);
      const p2 = project(corners[j][0], corners[j][1], corners[j][2], w, h);
      ctx.beginPath();
      ctx.moveTo(p1[0], p1[1]);
      ctx.lineTo(p2[0], p2[1]);
      ctx.stroke();
    });

    // 3. Draw toolhead marker and drop line
    const nx = (toolhead.x / bounds.x) * 2 - 1;
    const ny = (toolhead.y / bounds.y) * 2 - 1;
    const nz = (toolhead.z / bounds.z) * 2 - 1;

    const headP = project(nx, ny, nz, w, h);
    const floorP = project(nx, ny, -1, w, h);

    // Drop line
    ctx.strokeStyle = colors.drop;
    ctx.setLineDash([3, 3]);
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(floorP[0], floorP[1]);
    ctx.lineTo(headP[0], headP[1]);
    ctx.stroke();
    ctx.setLineDash([]);

    // Floor crosshair
    ctx.fillStyle = colors.drop;
    ctx.beginPath();
    ctx.arc(floorP[0], floorP[1], 3, 0, Math.PI * 2);
    ctx.fill();

    // Toolhead circle
    ctx.fillStyle = colors.head;
    ctx.beginPath();
    ctx.arc(headP[0], headP[1], 5, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 1;
    ctx.stroke();

    requestAnimationFrame(render);
  }

  window.redraw3D = () => {};
  render();

  // Spin Toggle Button
  const spinBtn = document.getElementById('btnSpinToggle');
  if (spinBtn) {
    spinBtn.addEventListener('click', () => {
      autoSpin = !autoSpin;
      spinBtn.textContent = `Auto-Spin: ${autoSpin ? 'ON' : 'OFF'}`;
      spinBtn.classList.toggle('tui-btn-primary', autoSpin);
    });
  }

  // Reset 3D View Button
  const resetBtn = document.getElementById('btnReset3D');
  if (resetBtn) {
    resetBtn.addEventListener('click', () => {
      yaw = 0.75;
      tilt = 0.55;
    });
  }

  // Jog interaction. The app starts at 1mm and shows the step in the middle
  // of the cross, so the demo does the same.
  let jogStep = 1;
  document.querySelectorAll('.step-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.step-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      jogStep = parseFloat(btn.dataset.step) || 1;
      const centre = document.getElementById('jogCenter');
      if (centre) centre.textContent = `${jogStep}mm`;
      const readout = document.querySelector('.jog-step-selector .accent-text');
      if (readout) readout.textContent = `${jogStep}mm`;
    });
  });

  function updateCoordsUI() {
    ['wireCoordX'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.textContent = toolhead.x.toFixed(1);
    });
    ['wireCoordY'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.textContent = toolhead.y.toFixed(1);
    });
    ['wireCoordZ'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.textContent = toolhead.z.toFixed(1);
    });
  }

  const jogXPlus = document.getElementById('jogXPlus');
  const jogXMinus = document.getElementById('jogXMinus');
  const jogYPlus = document.getElementById('jogYPlus');
  const jogYMinus = document.getElementById('jogYMinus');
  const jogZPlus = document.getElementById('jogZPlus');
  const jogZMinus = document.getElementById('jogZMinus');
  const jogCenter = document.getElementById('jogCenter');
  const jogHomeAll = document.getElementById('jogHomeAll');

  if (jogXPlus) jogXPlus.addEventListener('click', () => { toolhead.x = Math.min(bounds.x, toolhead.x + jogStep); updateCoordsUI(); });
  if (jogXMinus) jogXMinus.addEventListener('click', () => { toolhead.x = Math.max(0, toolhead.x - jogStep); updateCoordsUI(); });
  if (jogYPlus) jogYPlus.addEventListener('click', () => { toolhead.y = Math.min(bounds.y, toolhead.y + jogStep); updateCoordsUI(); });
  if (jogYMinus) jogYMinus.addEventListener('click', () => { toolhead.y = Math.max(0, toolhead.y - jogStep); updateCoordsUI(); });
  if (jogZPlus) jogZPlus.addEventListener('click', () => { toolhead.z = Math.min(bounds.z, toolhead.z + jogStep); updateCoordsUI(); });
  if (jogZMinus) jogZMinus.addEventListener('click', () => { toolhead.z = Math.max(0, toolhead.z - jogStep); updateCoordsUI(); });
  // The middle of the cross cycles the step size, as it does in the app.
  if (jogCenter) jogCenter.addEventListener('click', () => {
    const steps = [0.1, 1, 10, 50];
    const next = steps[(steps.indexOf(jogStep) + 1) % steps.length];
    const target = document.querySelector(`.step-btn[data-step="${next}"]`);
    if (target) target.click();
  });
  if (jogHomeAll) jogHomeAll.addEventListener('click', () => { toolhead.x = 0; toolhead.y = 0; toolhead.z = 0; updateCoordsUI(); });
}

/* --------------------------------------------------------------------------
   6. Sub-Pixel UTF-8 Braille Temperature Graph Simulator
   -------------------------------------------------------------------------- */
function initBrailleGraph() {
  const container = document.getElementById('brailleTextCanvas');
  if (!container) return;

  const DOTS = [
    [0x01, 0x02, 0x04, 0x40], // left column top->bottom
    [0x08, 0x10, 0x20, 0x80], // right column
  ];
  const BRAILLE_BASE = 0x2800;

  const width = 54;
  const height = 9;
  const subW = width * 2;
  const subH = height * 4;

  const extruderHistory = [];
  const bedHistory = [];

  // Generate baseline historical data
  for (let i = 0; i < subW; i++) {
    // Extruder heating up ramp then settling at 215°C
    const progress = i / subW;
    let extTemp;
    if (progress < 0.3) {
      extTemp = 25 + (215 - 25) * (progress / 0.3);
    } else {
      extTemp = 215 + (Math.sin(i * 0.4) * 0.4);
    }
    extruderHistory.push(extTemp);

    // Bed heating up to 60°C
    let bedTemp;
    if (progress < 0.2) {
      bedTemp = 22 + (60 - 22) * (progress / 0.2);
    } else {
      bedTemp = 60 + (Math.cos(i * 0.3) * 0.2);
    }
    bedHistory.push(bedTemp);
  }

  function renderBrailleCanvas() {
    // Cells grid: 2D array of dot bitmasks
    const grid = Array.from({ length: height }, () => Array(width).fill(0));

    function setSubpixel(sx, sy) {
      if (sx < 0 || sx >= subW || sy < 0 || sy >= subH) return;
      const cx = Math.floor(sx / 2);
      const cy = Math.floor(sy / 4);
      grid[cy][cx] |= DOTS[sx % 2][sy % 4];
    }

    // Map temperature (0°C - 260°C) to canvas subpixel Y (inverted)
    function tempToSubY(temp) {
      const normalized = Math.max(0, Math.min(260, temp)) / 260;
      return Math.floor((1 - normalized) * (subH - 1));
    }

    // Plot extruder line
    for (let x = 0; x < subW - 1; x++) {
      const y1 = tempToSubY(extruderHistory[x]);
      const y2 = tempToSubY(extruderHistory[x + 1]);
      setSubpixel(x, y1);
      // Fill small vertical step
      const step = y1 < y2 ? 1 : -1;
      for (let y = y1; y !== y2; y += step) {
        setSubpixel(x, y);
      }
    }

    // Plot bed line
    for (let x = 0; x < subW - 1; x++) {
      const y1 = tempToSubY(bedHistory[x]);
      setSubpixel(x, y1);
    }

    // Convert bitmasks to braille UTF-8 characters with axis labels
    const rows = [];
    const tempLabels = ['250°C', '200°C', '150°C', '100°C', ' 50°C', '  0°C'];
    for (let cy = 0; cy < height; cy++) {
      const chars = [];
      const label = cy % 2 === 0 && (cy / 2) < tempLabels.length ? tempLabels[cy / 2] : '     ';
      for (let cx = 0; cx < width; cx++) {
        const mask = grid[cy][cx];
        chars.push(mask === 0 ? ' ' : String.fromCharCode(BRAILLE_BASE + mask));
      }
      rows.push(`${label} ┤ ${chars.join('')}`);
    }
    rows.push(`       └${'─'.repeat(width)}`);
    rows.push(`       -120s                 -60s                  0s (now)`);

    container.textContent = rows.join('\n');
  }

  renderBrailleCanvas();

  // Tick temperature simulator
  setInterval(() => {
    const lastExt = extruderHistory[extruderHistory.length - 1];
    const newExt = 215 + (Math.sin(Date.now() / 1200) * 0.45);
    extruderHistory.shift();
    extruderHistory.push(newExt);

    const lastBed = bedHistory[bedHistory.length - 1];
    const newBed = 60.2 + (Math.cos(Date.now() / 2000) * 0.15);
    bedHistory.shift();
    bedHistory.push(newBed);

    const graphExtruderVal = document.getElementById('graphExtruderVal');
    const graphBedVal = document.getElementById('graphBedVal');
    const dashExtruderTemp = document.getElementById('dashExtruderTemp');
    const dashBedTemp = document.getElementById('dashBedTemp');

    if (graphExtruderVal) graphExtruderVal.textContent = `${newExt.toFixed(1)}°C`;
    if (graphBedVal) graphBedVal.textContent = `${newBed.toFixed(1)}°C`;
    if (dashExtruderTemp) dashExtruderTemp.textContent = newExt.toFixed(1);
    if (dashBedTemp) dashBedTemp.textContent = newBed.toFixed(1);

    renderBrailleCanvas();
  }, 1000);
}

/* --------------------------------------------------------------------------
   7. Color-Coded Bed Mesh Heightmap
   -------------------------------------------------------------------------- */
function initBedMesh() {
  const gridContainer = document.getElementById('heightmapGrid');
  if (!gridContainer) return;

  const size = 7;
  const meshValues = [
    [-0.042, -0.035, -0.021, -0.010, -0.018, -0.030, -0.045],
    [-0.030, -0.012,  0.008,  0.015,  0.010, -0.005, -0.028],
    [-0.015,  0.010,  0.028,  0.042,  0.032,  0.018, -0.010],
    [-0.005,  0.022,  0.048,  0.058,  0.045,  0.025,  0.002],
    [-0.012,  0.015,  0.035,  0.049,  0.038,  0.020, -0.008],
    [-0.028, -0.005,  0.012,  0.020,  0.014, -0.002, -0.022],
    [-0.040, -0.032, -0.018, -0.008, -0.015, -0.028, -0.038],
  ];

  function getMeshColor(val) {
    // Scale -0.05mm (blue #2196f3) -> 0.0mm (green #4caf50) -> +0.05mm (red #d41216)
    const norm = Math.max(-1, Math.min(1, val / 0.05));
    if (norm < 0) {
      // Blue to Green
      const t = norm + 1; // 0 to 1
      const r = Math.round(33 + t * (76 - 33));
      const g = Math.round(150 + t * (175 - 150));
      const b = Math.round(243 + t * (80 - 243));
      return `rgb(${r}, ${g}, ${b})`;
    } else {
      // Green to Red
      const t = norm; // 0 to 1
      const r = Math.round(76 + t * (212 - 76));
      const g = Math.round(175 - t * (175 - 18));
      const b = Math.round(80 - t * (80 - 22));
      return `rgb(${r}, ${g}, ${b})`;
    }
  }

  function renderGrid() {
    gridContainer.innerHTML = '';
    for (let r = 0; r < size; r++) {
      for (let c = 0; c < size; c++) {
        const val = meshValues[r][c];
        const cell = document.createElement('div');
        cell.className = 'mesh-cell';
        cell.style.backgroundColor = getMeshColor(val);
        cell.textContent = (val >= 0 ? '+' : '') + val.toFixed(2);
        cell.title = `Probe (${c}, ${r}): ${val.toFixed(3)} mm`;
        gridContainer.appendChild(cell);
      }
    }
  }

  renderGrid();

  // Calibration simulation button
  const calibrateBtn = document.getElementById('btnCalibrateMesh');
  if (calibrateBtn) {
    calibrateBtn.addEventListener('click', () => {
      calibrateBtn.textContent = 'Probing...';
      calibrateBtn.classList.add('tui-btn-danger');

      let step = 0;
      const total = size * size;
      const cells = gridContainer.querySelectorAll('.mesh-cell');

      cells.forEach(c => {
        c.style.opacity = '0.3';
        c.style.transform = 'scale(0.8)';
      });

      const interval = setInterval(() => {
        if (step < total) {
          cells[step].style.opacity = '1';
          cells[step].style.transform = 'scale(1)';
          step++;
        } else {
          clearInterval(interval);
          calibrateBtn.textContent = 'Calibrate Mesh';
          calibrateBtn.classList.remove('tui-btn-danger');
        }
      }, 40);
    });
  }
}

/* --------------------------------------------------------------------------
   8. Live Webcam Stream Simulator
   -------------------------------------------------------------------------- */
function initWebcamSimulator() {
  const canvas = document.getElementById('webcamSimCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  let active = true;
  let frame = 0;

  function renderWebcam() {
    if (!active) return;
    frame++;

    const w = canvas.width;
    const h = canvas.height;

    // Dark printer chamber background
    ctx.fillStyle = '#0a0d12';
    ctx.fillRect(0, 0, w, h);

    // Bed plate perspective
    ctx.fillStyle = '#1c2430';
    ctx.beginPath();
    ctx.moveTo(80, 220);
    ctx.lineTo(480, 220);
    ctx.lineTo(420, 100);
    ctx.lineTo(140, 100);
    ctx.closePath();
    ctx.fill();

    // Bed grid lines
    ctx.strokeStyle = '#2d3a4d';
    ctx.lineWidth = 1;
    for (let i = 1; i <= 5; i++) {
      const y = 100 + i * 20;
      ctx.beginPath();
      ctx.moveTo(140 - i * 10, y);
      ctx.lineTo(420 + i * 10, y);
      ctx.stroke();
    }

    // Printed part (Benchy outline simulation)
    ctx.fillStyle = '#e0754f';
    ctx.beginPath();
    ctx.rect(240, 120, 80, 50);
    ctx.fill();

    // Toolhead moving back and forth
    const toolX = 280 + Math.sin(frame * 0.08) * 50;
    const toolY = 115 + Math.cos(frame * 0.04) * 5;

    // Hotend nozzle
    ctx.fillStyle = '#f0d07a';
    ctx.beginPath();
    ctx.moveTo(toolX, toolY + 12);
    ctx.lineTo(toolX - 8, toolY);
    ctx.lineTo(toolX + 8, toolY);
    ctx.closePath();
    ctx.fill();

    // Stealthburner carriage
    ctx.fillStyle = '#221b1e';
    ctx.fillRect(toolX - 25, toolY - 35, 50, 35);
    ctx.fillStyle = '#a32638';
    ctx.fillRect(toolX - 12, toolY - 20, 24, 10);

    // Terminal scanline effect
    ctx.fillStyle = 'rgba(0, 0, 0, 0.2)';
    for (let y = 0; y < h; y += 4) {
      ctx.fillRect(0, y, w, 2);
    }

    requestAnimationFrame(renderWebcam);
  }

  renderWebcam();

  const pauseBtn = document.getElementById('btnPauseWebcam');
  if (pauseBtn) {
    pauseBtn.addEventListener('click', () => {
      active = !active;
      pauseBtn.textContent = active ? 'Pause' : 'Resume';
      if (active) renderWebcam();
    });
  }
}

/* --------------------------------------------------------------------------
   9. Shortcuts Search / Filter
   -------------------------------------------------------------------------- */
function initShortcutsFilter() {
  const searchInput = document.getElementById('shortcutSearchInput');
  const table = document.getElementById('shortcutsTable');
  if (!searchInput || !table) return;

  searchInput.addEventListener('input', (e) => {
    const q = e.target.value.toLowerCase().trim();
    const rows = table.querySelectorAll('tbody tr');

    rows.forEach(row => {
      const text = row.textContent.toLowerCase();
      row.style.display = text.includes(q) ? '' : 'none';
    });
  });
}

/* --------------------------------------------------------------------------
   10. Live Statusbar Clock
   -------------------------------------------------------------------------- */
function initLiveClock() {
  const clockEl = document.getElementById('terminalTimeClock');
  if (!clockEl) return;

  function updateClock() {
    const now = new Date();
    clockEl.textContent = now.toTimeString().split(' ')[0];
  }

  updateClock();
  setInterval(updateClock, 1000);
}


/* --------------------------------------------------------------------------
   9. Braille canvas
   --------------------------------------------------------------------------
   A port of klipper_tui/braille.py. Each character cell carries a 2x4 grid of
   dots, so a drawing made this way has four times the vertical resolution of
   one built from block characters. A cell can hold only one colour, so
   overlapping strokes are resolved by draw order — later wins, same as the
   app.
   -------------------------------------------------------------------------- */
const BRAILLE_DOTS = [
  [0x01, 0x02, 0x04, 0x40], // left column, top to bottom
  [0x08, 0x10, 0x20, 0x80], // right column
];
const BRAILLE_BASE = 0x2800;

function BrailleCanvas(width, height) {
  this.width = width;
  this.height = height;
  this.subWidth = width * 2;
  this.subHeight = height * 4;
  this.mask = new Uint8Array(width * height);
  this.color = new Array(width * height).fill(null);
}

BrailleCanvas.prototype.set = function (sx, sy, color) {
  sx = Math.round(sx);
  sy = Math.round(sy);
  if (sx < 0 || sy < 0 || sx >= this.subWidth || sy >= this.subHeight) return;
  const cx = sx >> 1;
  const cy = sy >> 2;
  const at = cy * this.width + cx;
  this.mask[at] |= BRAILLE_DOTS[sx & 1][sy & 3];
  this.color[at] = color;
};

BrailleCanvas.prototype.line = function (sx0, sy0, sx1, sy1, color) {
  sx0 = Math.round(sx0); sy0 = Math.round(sy0);
  sx1 = Math.round(sx1); sy1 = Math.round(sy1);
  const dx = Math.abs(sx1 - sx0);
  const dy = -Math.abs(sy1 - sy0);
  const stepX = sx0 < sx1 ? 1 : -1;
  const stepY = sy0 < sy1 ? 1 : -1;
  let err = dx + dy;
  for (;;) {
    this.set(sx0, sy0, color);
    if (sx0 === sx1 && sy0 === sy1) return;
    const err2 = 2 * err;
    if (err2 >= dy) { err += dy; sx0 += stepX; }
    if (err2 <= dx) { err += dx; sy0 += stepY; }
  }
};

/** One HTML string, with runs of equal colour merged into a single span. */
BrailleCanvas.prototype.renderHTML = function () {
  const rows = [];
  for (let cy = 0; cy < this.height; cy++) {
    let out = '';
    let runColor = null;
    let run = '';
    const flush = () => {
      if (!run) return;
      out += runColor ? `<span style="color:${runColor}">${run}</span>` : run;
      run = '';
    };
    for (let cx = 0; cx < this.width; cx++) {
      const at = cy * this.width + cx;
      const bits = this.mask[at];
      const char = bits ? String.fromCharCode(BRAILLE_BASE + bits) : ' ';
      const color = bits ? this.color[at] : null;
      if (color !== runColor) { flush(); runColor = color; }
      run += char;
    }
    flush();
    rows.push(out);
  }
  return rows.join('\n');
};

/* --------------------------------------------------------------------------
   10. Toolpath Viewer
   --------------------------------------------------------------------------
   The app reads the running gcode over HTTP range requests and draws the
   current layer into a braille canvas, colouring what the nozzle has already
   laid down differently from what is still ahead of it. This draws the same
   way, into the same kind of canvas — there is just no gcode behind it, so
   the layer is generated: three perimeters around a blob that changes shape
   with height, plus zig-zag infill clipped to it.
   -------------------------------------------------------------------------- */
function initToolpathViewer() {
  const view = document.getElementById('toolpathView');
  if (!view) return;

  // Cells, not pixels. The app's panel is about this size on a wide terminal.
  const COLS = 104;
  const ROWS = 26;
  const TOTAL_LAYERS = 103;

  let layer = 42;
  let zoom = 1;
  let pan = { x: 0, y: 0 };
  let follow = true;
  let progress = 0.61;

  function outline(index, inset, steps) {
    const points = [];
    const count = steps || 220;
    const wobble = 0.35 + 0.1 * Math.sin(index / 9);
    const twist = index / 26;
    for (let i = 0; i <= count; i++) {
      const t = (i / count) * Math.PI * 2;
      const r = 1
        + wobble * Math.sin(3 * t + twist)
        + 0.12 * Math.sin(7 * t - twist * 2);
      points.push([Math.cos(t) * (r - inset), Math.sin(t) * (r - inset)]);
    }
    return points;
  }

  function inside(polygon, x, y) {
    let hit = false;
    for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
      const [xi, yi] = polygon[i];
      const [xj, yj] = polygon[j];
      if ((yi > y) !== (yj > y) &&
          x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) {
        hit = !hit;
      }
    }
    return hit;
  }

  /** Perimeters first, then infill, in the order a slicer emits them. */
  function buildLayer(index) {
    const strokes = [];
    for (let shell = 0; shell < 3; shell++) {
      strokes.push(outline(index, shell * 0.075));
    }

    // The clip polygon is only used for point-in-polygon tests, once per
    // candidate infill sample. At full resolution that is a couple of million
    // edge crossings per layer; a coarser loop is indistinguishable here.
    const shape = outline(index, 0.24, 72);
    const angle = (index % 2 ? 45 : -45) * Math.PI / 180;
    const cos = Math.cos(angle);
    const sin = Math.sin(angle);
    let flip = false;
    for (let u = -2; u <= 2; u += 0.085) {
      let run = [];
      for (let v = -2; v <= 2; v += 0.03) {
        const x = u * cos - v * sin;
        const y = u * sin + v * cos;
        if (inside(shape, x, y)) {
          run.push([x, y]);
        } else {
          if (run.length > 1) strokes.push(flip ? run.reverse() : run);
          run = [];
        }
      }
      if (run.length > 1) strokes.push(flip ? run.reverse() : run);
      flip = !flip;
    }
    return strokes;
  }

  let strokes = buildLayer(layer);
  const pointCount = () => strokes.reduce((n, s) => n + s.length, 0);

  function themeColors() {
    const style = getComputedStyle(document.documentElement);
    return {
      done: style.getPropertyValue('--path-done').trim() || '#d1553d',
      todo: style.getPropertyValue('--path-todo').trim() || '#5c4a52',
      head: style.getPropertyValue('--path-head').trim() || '#e0a13c',
    };
  }

  function render() {
    const canvas = new BrailleCanvas(COLS, ROWS);
    const colors = themeColors();

    // The frame is fixed rather than per-layer, so stepping through layers
    // does not make the view jump about. Same reason the app frames on the
    // whole file rather than the layer in front of it.
    const span = 3.1;
    const scale = Math.min(canvas.subWidth / span, canvas.subHeight / span)
      * 0.96 * zoom;
    const offX = (canvas.subWidth - span * scale) / 2 + pan.x * canvas.subWidth;
    const offY = (canvas.subHeight - span * scale) / 2 + pan.y * canvas.subHeight;
    // Bed Y grows away from the viewer; screen Y grows downward.
    const place = (p) => [
      offX + (p[0] + span / 2) * scale,
      canvas.subHeight - offY - (p[1] + span / 2) * scale,
    ];

    const total = pointCount();
    const printed = Math.floor(total * progress);
    let seen = 0;
    let head = null;

    for (const stroke of strokes) {
      for (let i = 1; i < stroke.length; i++) {
        const laid = seen + i <= printed;
        const [x0, y0] = place(stroke[i - 1]);
        const [x1, y1] = place(stroke[i]);
        canvas.line(x0, y0, x1, y1, laid ? colors.done : colors.todo);
        if (laid) head = [x1, y1];
      }
      seen += stroke.length;
    }

    if (head) {
      const [hx, hy] = head;
      for (let d = -2; d <= 2; d++) {
        canvas.set(hx + d, hy, colors.head);
        canvas.set(hx, hy + d, colors.head);
      }
    }

    view.innerHTML = canvas.renderHTML();

    const set = (id, text) => {
      const el = document.getElementById(id);
      if (el) el.textContent = text;
    };
    set('tpDone', printed);
    set('tpTotal', '/' + total);
    set('tpLayer', layer);
    set('tpZ', (layer * 0.2).toFixed(2));
    set('tpZoom', zoom.toFixed(1));
    const state = document.getElementById('tpState');
    if (state) {
      state.textContent = follow ? 'following' : 'held';
      state.className = follow ? 'ok' : 'held';
    }
  }

  function step(by) {
    layer = Math.max(1, Math.min(TOTAL_LAYERS, layer + by));
    follow = false;
    strokes = buildLayer(layer);
    render();
  }

  const on = (id, fn) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('click', fn);
  };

  on('tpPrev', () => step(-1));
  on('tpNext', () => step(1));
  on('tpZoomIn', () => { zoom = Math.min(6, zoom * 1.25); render(); });
  on('tpZoomOut', () => { zoom = Math.max(0.5, zoom / 1.25); render(); });
  on('tpFit', () => { zoom = 1; pan = { x: 0, y: 0 }; render(); });
  on('tpPanLeft', () => { pan.x += 0.15 / zoom; render(); });
  on('tpPanRight', () => { pan.x -= 0.15 / zoom; render(); });
  on('tpPanUp', () => { pan.y -= 0.15 / zoom; render(); });
  on('tpPanDown', () => { pan.y += 0.15 / zoom; render(); });
  on('tpFollow', () => { follow = !follow; render(); });

  // Clicking centres what was clicked, as the app does.
  view.addEventListener('click', (event) => {
    const rect = view.getBoundingClientRect();
    pan.x -= (event.clientX - rect.left) / rect.width - 0.5;
    pan.y -= (event.clientY - rect.top) / rect.height - 0.5;
    render();
  });

  setInterval(() => {
    if (!follow) return;
    progress += 0.012;
    if (progress >= 1) {
      progress = 0;
      layer = layer >= TOTAL_LAYERS ? 1 : layer + 1;
      strokes = buildLayer(layer);
    }
    render();
  }, 140);

  render();
}


/* --------------------------------------------------------------------------
   11. Screenshot lightbox
   --------------------------------------------------------------------------
   The screenshots are terminal captures, so the detail people want to look at
   is the text — which is unreadable at grid size. Clicking one opens it as
   large as the viewport allows, with its caption, and the arrows walk through
   the rest without going back to the grid.
   -------------------------------------------------------------------------- */
function initLightbox() {
  const box = document.getElementById('lightbox');
  const image = document.getElementById('lightboxImage');
  const caption = document.getElementById('lightboxCaption');
  const closeBtn = document.getElementById('lightboxClose');
  const prevBtn = document.getElementById('lightboxPrev');
  const nextBtn = document.getElementById('lightboxNext');
  if (!box || !image) return;

  const triggers = Array.from(document.querySelectorAll('.shot-open'));
  if (!triggers.length) return;

  let index = 0;
  let openedFrom = null;

  function show(at) {
    index = (at + triggers.length) % triggers.length;
    const trigger = triggers[index];
    const source = trigger.querySelector('img');
    image.src = source.getAttribute('src');
    image.alt = source.getAttribute('alt') || '';
    // The caption lives beside the button, in the figure that wraps both.
    const figcaption = trigger.closest('figure')?.querySelector('figcaption');
    caption.innerHTML = figcaption ? figcaption.innerHTML : '';
  }

  function open(at) {
    openedFrom = triggers[at];
    show(at);
    box.hidden = false;
    // Stop the page behind from scrolling under the overlay.
    document.body.style.overflow = 'hidden';
    closeBtn.focus();
  }

  function close() {
    box.hidden = true;
    document.body.style.overflow = '';
    image.removeAttribute('src');
    if (openedFrom) openedFrom.focus();
    openedFrom = null;
  }

  triggers.forEach((trigger, at) => {
    trigger.addEventListener('click', () => open(at));
  });

  closeBtn.addEventListener('click', close);
  prevBtn.addEventListener('click', () => show(index - 1));
  nextBtn.addEventListener('click', () => show(index + 1));

  // Clicking the backdrop closes; clicking the picture itself does not.
  box.addEventListener('click', (event) => {
    if (event.target === box) close();
  });

  document.addEventListener('keydown', (event) => {
    if (box.hidden) return;
    if (event.key === 'Escape') {
      close();
    } else if (event.key === 'ArrowLeft') {
      show(index - 1);
    } else if (event.key === 'ArrowRight') {
      show(index + 1);
    } else if (event.key === 'Tab') {
      // Keep focus inside the dialog while it is open.
      const stops = [closeBtn, prevBtn, nextBtn];
      const at = stops.indexOf(document.activeElement);
      const step = event.shiftKey ? -1 : 1;
      stops[(Math.max(0, at) + step + stops.length) % stops.length].focus();
      event.preventDefault();
    }
  });
}
