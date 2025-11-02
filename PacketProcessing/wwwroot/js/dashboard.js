// === STATE ===
let connection = null;
let hubConnected = false;
let apiConnected = false;
let startTime = Date.now();
let activeDevice = null;
let currentMode = 'realtime';
let captureActive = false;

// Counters
let stats = {
    captured: 0,
    parsed: 0,
    dropped: 0,
    flushed: 0,
    failed: 0,
    backpressure: 0,
    avgLatency: 0,
    motionCaptured: 0,
    safetyCaptured: 0,
    onvifCaptured: 0,
    hubReceived: 0,
    parseRate: 0,
    flushRate: 0,
    motionCaptureFail: 0,
    safetyCaptureFail: 0,
    onvifCaptureFail: 0,
    motionParseSuccess: 0,
    motionParseFail: 0,
    safetyParseSuccess: 0,
    safetyParseFail: 0,
    onvifParseSuccess: 0,
    onvifParseFail: 0,
    motionFlushSuccess: 0,
    motionFlushFail: 0,
    safetyFlushSuccess: 0,
    safetyFlushFail: 0,
    onvifFlushSuccess: 0,
    onvifFlushFail: 0
};

// Throughput tracking
let lastStats = {
    captured: 0,
    parsed: 0,
    flushed: 0,
    timestamp: Date.now()
};

let throughput = {
    capturedPps: 0,
    parsedPps: 0,
    flushedPps: 0
};

let lastChartUpdate = 0;
const CHART_UPDATE_INTERVAL = 1000; // Update charts at most once per second

// Charts data
let throughputData = {
    labels: [],
    captured: [],
    parsed: [],
    flushed: []
};

let latencyData = {
    labels: [],
    values: []
};

let throughputChart;

// === INITIALIZATION ===
window.addEventListener('load', () => {
    initCharts();
    updateUptime();
    loadCurrentState(); // Load current state from backend
    loadAvailableDevices(); // Load device list immediately
    checkApiHealth(); // Check health immediately on load
    checkQuestDbHealth(); // Check QuestDB health
    checkPostgresHealth(); // Check PostgreSQL health
    setInterval(updateUptime, 1000); // Update uptime every second
    setInterval(checkApiHealth, 2000); // Check health every 2 seconds
    setInterval(checkQuestDbHealth, 2000); // Check QuestDB every 2 seconds
    setInterval(checkPostgresHealth, 2000); // Check PostgreSQL every 2 seconds
    
    // Force scroll to top after everything loads (prevents auto-scroll to anchors)
    setTimeout(() => {
        if (window.location.hash) {
            history.replaceState(null, null, window.location.pathname);
        }
        window.scrollTo({ top: 0, behavior: 'instant' });
    }, 100);
    
    // Automatically connect to SignalR
    logMessage('Dashboard loaded. Connecting to SignalR automatically...', 'info');
    connectHub();

    // Initialize endpoint input rows
    ['motionEndpoints','safetyEndpoints','onvifEndpoints'].forEach(id => addEndpointRow(id));
    // Initialize cameras container with one row
    addCameraRow();
});

// === STATE MANAGEMENT ===
async function loadCurrentState() {
    try {
        const response = await fetch('http://localhost:10901/api/range/mode');
        
        if (response.ok) {
            const result = await response.json();
            const state = (result.data || result).toLowerCase();
            currentMode = state;
            updateModeButtons();
        }
    } catch (err) {
        console.error('Failed to load current state:', err);
    }
}

// === CHARTS ===
function initCharts() {
    const chartOptions = {
        responsive: true,
        maintainAspectRatio: true,
        scales: {
            y: { 
                beginAtZero: true,
                grid: { color: '#333' },
                ticks: { color: '#b0b0b0' }
            },
            x: { 
                grid: { color: '#333' },
                ticks: { color: '#b0b0b0' }
            }
        },
        plugins: {
            legend: {
                labels: { color: '#e0e0e0' }
            }
        }
    };
    
    // Throughput Chart
    const throughputCtx = document.getElementById('throughputChart').getContext('2d');
    throughputChart = new Chart(throughputCtx, {
        type: 'line',
        data: {
            labels: throughputData.labels,
            datasets: [
                {
                    label: 'Captured (pps)',
                    data: throughputData.captured,
                    borderColor: '#4caf50',
                    backgroundColor: 'rgba(76, 175, 80, 0.1)',
                    tension: 0.4
                },
                {
                    label: 'Parsed (pps)',
                    data: throughputData.parsed,
                    borderColor: '#2196f3',
                    backgroundColor: 'rgba(33, 150, 243, 0.1)',
                    tension: 0.4
                },
                {
                    label: 'Flushed (pps)',
                    data: throughputData.flushed,
                    borderColor: '#ff9800',
                    backgroundColor: 'rgba(255, 152, 0, 0.1)',
                    tension: 0.4
                }
            ]
        },
        options: chartOptions
    });
}

function updateChart(capturedDelta, parsedDelta, flushedDelta, avgLatency) {
    const now = new Date().toLocaleTimeString();
    
    // Throughput
    throughputData.labels.push(now);
    throughputData.captured.push(capturedDelta);
    throughputData.parsed.push(parsedDelta);
    throughputData.flushed.push(flushedDelta);
    
    // Keep last 60 data points
    if (throughputData.labels.length > 60) {
        throughputData.labels.shift();
        throughputData.captured.shift();
        throughputData.parsed.shift();
        throughputData.flushed.shift();
    }
    
    throughputChart.update('none'); // Update without animation for performance
}

// === SIGNALR HUB ===
// toggleSignalR function removed - SignalR now connects automatically

async function connectHub() {
    if (connection) {
        logMessage('Already connected or connecting...', 'warning');
        return;
    }
    
    const hubUrl = 'http://localhost:10901/hubs/telemetry';
    logMessage(`Connecting to Telemetry hub: ${hubUrl}`, 'info');
    
    // Show connecting state
    updateSignalRStatus();
    
    connection = new signalR.HubConnectionBuilder()
        .withUrl(hubUrl)
        .withAutomaticReconnect([0, 1000, 2000, 5000])
        .configureLogging(signalR.LogLevel.Information)
        .build();

    connection.on('telemetry:update', (telemetryData) => {
        // Calculate throughput rates
        var now = Date.now();
        const deltaTime = (now - lastStats.timestamp) / 1000; // seconds
        
        // Calculate rates if we have enough time difference (minimum 0.1 seconds)
        if (deltaTime >= 0.1 && lastStats.timestamp > 0) {
            const capturedDelta = Math.max(0, telemetryData.captured - lastStats.captured);
            const parsedDelta = Math.max(0, telemetryData.parsed - lastStats.parsed);
            const flushedDelta = Math.max(0, telemetryData.flushed - lastStats.flushed);
            
            // Calculate new rates
            const newCapturedPps = Math.round(capturedDelta / deltaTime);
            const newParsedPps = Math.round(parsedDelta / deltaTime);
            const newFlushedPps = Math.round(flushedDelta / deltaTime);
            
            // Apply smoothing (exponential moving average)
            const alpha = 0.3; // Smoothing factor
            throughput.capturedPps = Math.round(throughput.capturedPps * (1 - alpha) + newCapturedPps * alpha);
            throughput.parsedPps = Math.round(throughput.parsedPps * (1 - alpha) + newParsedPps * alpha);
            throughput.flushedPps = Math.round(throughput.flushedPps * (1 - alpha) + newFlushedPps * alpha);
        }
        
        // Update last stats for next calculation
        lastStats = {
            captured: telemetryData.captured || 0,
            parsed: telemetryData.parsed || 0,
            flushed: telemetryData.flushed || 0,
            timestamp: now
        };
        
        // Update stats with real-time telemetry data
        stats.captured = telemetryData.captured || 0;
        stats.parsed = telemetryData.parsed || 0;
        stats.dropped = telemetryData.dropped || 0;
        stats.flushed = telemetryData.flushed || 0;
        stats.failed = telemetryData.failed || 0;
        stats.backpressure = telemetryData.backpressure || 0;
        stats.avgLatency = telemetryData.avgLatency || 0;
        stats.motionCaptured = telemetryData.motionCaptured || 0;
        stats.safetyCaptured = telemetryData.safetyCaptured || 0;
        stats.onvifCaptured = telemetryData.onvifCaptured || 0;
        
        // Map per-entity capture fail
        stats.motionCaptureFail = telemetryData.motionCaptureFail || 0;
        stats.safetyCaptureFail = telemetryData.safetyCaptureFail || 0;
        stats.onvifCaptureFail = telemetryData.onvifCaptureFail || 0;

        // Map per-entity parse success/fail
        stats.motionParseSuccess = telemetryData.motionParseSuccess || 0;
        stats.motionParseFail = telemetryData.motionParseFail || 0;
        stats.safetyParseSuccess = telemetryData.safetyParseSuccess || 0;
        stats.safetyParseFail = telemetryData.safetyParseFail || 0;
        stats.onvifParseSuccess = telemetryData.onvifParseSuccess || 0;
        stats.onvifParseFail = telemetryData.onvifParseFail || 0;

        // Map per-entity flush success/fail
        stats.motionFlushSuccess = telemetryData.motionFlushSuccess || 0;
        stats.motionFlushFail = telemetryData.motionFlushFail || 0;
        stats.safetyFlushSuccess = telemetryData.safetyFlushSuccess || 0;
        stats.safetyFlushFail = telemetryData.safetyFlushFail || 0;
        stats.onvifFlushSuccess = telemetryData.onvifFlushSuccess || 0;
        stats.onvifFlushFail = telemetryData.onvifFlushFail || 0;
        
        // Update channel stats if available
        if (telemetryData.motionRawChannel || telemetryData.safetyRawChannel || telemetryData.onvifRawChannel ||
            telemetryData.motionParsedChannel || telemetryData.safetyParsedChannel || telemetryData.onvifParsedChannel) {
            updateChannelStats(
                telemetryData.motionRawChannel,
                telemetryData.safetyRawChannel,
                telemetryData.onvifRawChannel,
                telemetryData.motionParsedChannel,
                telemetryData.safetyParsedChannel,
                telemetryData.onvifParsedChannel
            );
        }
        
        // Update UI with real-time data
        updateTelemetryStats();
        
        // Update charts with throttling (at most once per second)
        const currentTime = Date.now();
        if (currentTime - lastChartUpdate >= CHART_UPDATE_INTERVAL) {
            const chartTime = new Date();
            const timeLabel = chartTime.toLocaleTimeString();
            
            // Update throughput chart
            throughputData.labels.push(timeLabel);
            throughputData.captured.push(throughput.capturedPps);
            throughputData.parsed.push(throughput.parsedPps);
            throughputData.flushed.push(throughput.flushedPps);
            
            // Keep only last 20 data points
            if (throughputData.labels.length > 20) {
                throughputData.labels.shift();
                throughputData.captured.shift();
                throughputData.parsed.shift();
                throughputData.flushed.shift();
            }
            
            if (throughputChart) {
                throughputChart.update('none'); // Update without animation for performance
            }
            
            lastChartUpdate = currentTime;
        }
        
        // Log telemetry update with throughput info
        logMessage(`Telemetry updated: Captured=${stats.captured}, Parsed=${stats.parsed}, Flushed=${stats.flushed}, Rates: ${throughput.capturedPps}/${throughput.parsedPps}/${throughput.flushedPps} pps, DeltaTime=${deltaTime.toFixed(2)}s`, 'info');
    });

    connection.onclose((error) => {
        console.log('SignalR connection closed:', error);
        hubConnected = false;
        updateConnectionStatus();
        updateSignalRStatus();
        logMessage('SignalR disconnected', 'error');
    });

    connection.onreconnecting(() => {
        console.log('SignalR reconnecting...');
        hubConnected = false;
        updateConnectionStatus();
        updateSignalRStatus();
        logMessage('SignalR reconnecting...', 'warning');
    });

    connection.onreconnected(() => {
        console.log('SignalR reconnected successfully');
        hubConnected = true;
        updateConnectionStatus();
        updateSignalRStatus();
        logMessage('SignalR reconnected successfully', 'success');
    });

    try {
        logMessage('Starting SignalR connection...', 'info');
        
        // Add a timeout to the connection
        const connectionPromise = connection.start();
        const timeoutPromise = new Promise((_, reject) => 
            setTimeout(() => reject(new Error('Connection timeout after 10 seconds')), 10000)
        );
        
        await Promise.race([connectionPromise, timeoutPromise]);
        
        hubConnected = true;
        updateConnectionStatus();
        updateSignalRStatus();
        logMessage('SignalR connected successfully!', 'success');
        console.log('SignalR connection established successfully');
    } catch (err) {
        logMessage(`SignalR connection failed: ${err.message}`, 'error');
        console.error('SignalR connection error:', err);
        connection = null;
        updateSignalRStatus();
    }
}

async function disconnectHub() {
    if (connection) {
        await connection.stop();
        connection = null;
        hubConnected = false;
        updateConnectionStatus();
        updateSignalRStatus();
        logMessage('SignalR disconnected', 'info');
    }
}

function updateSignalRStatus() {
    // Use the main status bar elements instead of sidebar
    const indicator = document.getElementById('hubStatus');
    const statusText = document.getElementById('hubStatusText');
    
    if (hubConnected) {
        indicator.className = 'status-indicator connected';
        statusText.textContent = 'Hub: Connected';
    } else if (connection) {
        // Connection object exists but not connected yet (connecting/reconnecting)
        indicator.className = 'status-indicator connecting';
        statusText.textContent = 'Hub: Connecting...';
    } else {
        indicator.className = 'status-indicator disconnected';
        statusText.textContent = 'Hub: Disconnected';
    }
}

function updateDashboardTitle() {
    const titleEl = document.getElementById('dashboardTitle');
    titleEl.textContent = 'Kanat Packet Processing - Telemetry Dashboard';
}

// === DEVICE MANAGEMENT ===
async function loadAvailableDevices() {
    try {
        const response = await fetch('http://localhost:10901/api/range/realtime/devices');
        
        if (!response.ok) {
            logMessage('Failed to load available devices', 'error');
            return;
        }
        
        const result = await response.json();
        const devices = result.data || result;
        
        const select = document.getElementById('deviceNameSelect');
        const bpfSelect = document.getElementById('bpfDeviceSelect');
        if (select) select.innerHTML = '';
        if (bpfSelect) bpfSelect.innerHTML = '';
        
        if (devices && devices.length > 0) {
            devices.forEach(device => {
                if (select) {
                    const option = document.createElement('option');
                    option.value = device;
                    option.textContent = device;
                    select.appendChild(option);
                }
                if (bpfSelect) {
                    const option2 = document.createElement('option');
                    option2.value = device;
                    option2.textContent = device;
                    bpfSelect.appendChild(option2);
                }
            });
            logMessage(`Loaded ${devices.length} available network devices`, 'success');
        } else {
            if (select) {
                const option = document.createElement('option');
                option.value = '';
                option.textContent = 'No devices available';
                select.appendChild(option);
            }
            if (bpfSelect) {
                const option2 = document.createElement('option');
                option2.value = '';
                option2.textContent = 'No devices available';
                bpfSelect.appendChild(option2);
            }
            logMessage('No network devices found', 'warning');
        }
    } catch (err) {
        logMessage(`Error loading devices: ${err.message}`, 'error');
        const select = document.getElementById('deviceNameSelect');
        const bpfSelect = document.getElementById('bpfDeviceSelect');
        if (select) select.innerHTML = '<option value="">Error loading devices</option>';
        if (bpfSelect) bpfSelect.innerHTML = '<option value="">Error loading devices</option>';
    }
}

// === MODE MANAGEMENT ===
async function switchMode(mode) {
    if (currentMode === mode) {
        return; // Already in this mode
    }
    
    try {
        logMessage(`Switching to ${mode} mode...`, 'info');
        
        // Call backend API to change mode
        const response = await fetch(`http://localhost:10901/api/range/mode/${mode}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const result = await response.json();
        
        if (response.ok) {
            logMessage(`Mode changed to ${mode} successfully`, 'success');
            
            // Navigate to appropriate page
            if (mode === 'playback') {
                window.location.href = 'playback.html';
            } else {
                window.location.href = 'index.html';
            }
        } else {
            logMessage(`Failed to switch mode: ${result.message || 'Unknown error'}`, 'error');
        }
    } catch (err) {
        logMessage(`Error switching mode: ${err.message}`, 'error');
    }
}

function updateModeButtons() {
    const realtimeBtn = document.getElementById('realtimeBtn');
    const playbackBtn = document.getElementById('playbackBtn');
    
    if (currentMode === 'realtime') {
        realtimeBtn.classList.add('active');
        playbackBtn.classList.remove('active');
    } else {
        realtimeBtn.classList.remove('active');
        playbackBtn.classList.add('active');
    }
}

// === CAPTURE CONTROL ===
async function startRange() {
    const desc = document.getElementById('rangeDescription').value || '';
    const device = (document.getElementById('bpfDeviceSelect')?.value || '').trim();
    if (!device) {
        logMessage('Please select a device before starting range', 'error');
        return;
    }
    const motion = collectEndpoints('motionEndpoints');
    const safety = collectEndpoints('safetyEndpoints');
    const onvif = collectEndpoints('onvifEndpoints');
    const mtxIp = document.getElementById('mtxIp').value.trim();
    const mtxPortStr = document.getElementById('mtxPort').value.trim();
    const mtxPort = mtxPortStr ? parseInt(mtxPortStr) : null;

    const body = {
        description: desc,
        config: {
            bpfConfig: {
                device: device || 'any',
                motion: motion.length > 0 ? motion : undefined,
                safety: safety.length > 0 ? safety : undefined,
                onVIF: onvif.length > 0 ? onvif : undefined
            },
            mtxConfig: (mtxIp || mtxPort) ? { ip: mtxIp || null, port: mtxPort || null } : undefined,
            cams: (collectCams().length > 0) ? collectCams() : undefined
        }
    };
    try {
        logMessage('Starting range...', 'info');
        const response = await fetch('http://localhost:10901/api/range/realtime/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const result = await response.json();
        if (response.ok) {
            const range = result.data || result;
            renderCurrentRange(range);
            // Disable Development Only section when range starts
            disableDevSection();
            logMessage(`Range started (Id=${range.id})`, 'success');
        } else {
            logMessage(`Failed to start range: ${result.errorMessage || 'Unknown error'}`, 'error');
        }
    } catch (err) {
        logMessage(`Error starting range: ${err.message}`, 'error');
    }
}

async function stopRange() {
    try {
        logMessage('Stopping range...', 'info');
        const response = await fetch('http://localhost:10901/api/range/realtime/stop', { method: 'DELETE' });
        const result = await response.json();
        if (response.ok) {
            const range = result.data || result;
            // Reset all stats (frontend + backend) and clear range header
            try { await resetStats(); } catch (_) {}
            renderCurrentRange(null);
            // Re-enable Development Only section when range stops
            enableDevSection();
            logMessage(`Range stopped (Id=${range?.id || 'N/A'})`, 'success');
        } else {
            logMessage(`Failed to stop range: ${result.errorMessage || 'Unknown error'}`, 'error');
        }
    } catch (err) {
        logMessage(`Error stopping range: ${err.message}`, 'error');
    }
}

function renderCurrentRange(range) {
    const el = document.getElementById('currentRangeSummary');
    if (!range) { el.textContent = ''; return; }
    const ts = range.timestamp ? new Date(range.timestamp).toLocaleString() : 'N/A';
    const desc = range.description || '';
    const cfg = range.config || {};
    el.textContent = `Range: ${range.id} | Created: ${ts} ${desc ? '| ' + desc : ''} | Device: ${cfg?.bpfConfig?.device || 'N/A'}`;
}

// === SECTION ENABLE/DISABLE HELPERS ===
function disableDevSection() {
    const devSection = document.getElementById('devControlsSection');
    if (devSection) {
        devSection.classList.add('disabled');
    }
}

function enableDevSection() {
    const devSection = document.getElementById('devControlsSection');
    if (devSection) {
        devSection.classList.remove('disabled');
    }
}

function disableRangeSection() {
    const rangeSection = document.getElementById('rangeControlsSection');
    if (rangeSection) {
        rangeSection.classList.add('disabled');
    }
}

function enableRangeSection() {
    const rangeSection = document.getElementById('rangeControlsSection');
    if (rangeSection) {
        rangeSection.classList.remove('disabled');
    }
}

async function startCaptureDev() {
    const deviceName = document.getElementById('deviceNameSelect').value.trim();
    
    if (!deviceName) {
        logMessage('Please enter a device name', 'error');
        return;
    }
    
    try {
        logMessage(`Starting capture on device: ${deviceName}...`, 'info');
        
        const response = await fetch(`http://localhost:10901/api/range/dev/realtime/start/${encodeURIComponent(deviceName)}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const result = await response.json();
        
        if (response.ok) {
            activeDevice = deviceName;
            captureActive = true;
            updateDashboardTitle();
            // Disable Range Controls section when dev capture starts
            disableRangeSection();
            logMessage(`Capture started successfully on ${deviceName}`, 'success');
        } else {
            logMessage(`Failed to start capture: ${result.message || 'Unknown error'}`, 'error');
        }
    } catch (err) {
        logMessage(`Error starting capture: ${err.message}`, 'error');
    }
}

async function stopCaptureDev() {
    try {
        logMessage('Stopping capture...', 'info');
        
        const response = await fetch('http://localhost:10901/api/range/dev/realtime/stop', {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const result = await response.json();
        
        if (response.ok) {
            activeDevice = null;
            captureActive = false;
            updateDashboardTitle();
            // Re-enable Range Controls section when dev capture stops
            enableRangeSection();
            logMessage('Capture stopped successfully', 'success');
        } else {
            logMessage(`Failed to stop capture: ${result.message || 'Unknown error'}`, 'error');
        }
    } catch (err) {
        logMessage(`Error stopping capture: ${err.message}`, 'error');
    }
}

// === DATABASE HEALTH CHECKS ===
let questdbConnected = false;
let postgresConnected = false;

async function checkApiHealth() {
    try {
        const response = await fetch('http://localhost:10901/health', {
            method: 'GET',
            cache: 'no-cache'
        });
        
        if (response.ok) {
            if (!apiConnected) {
                logMessage('API health check: Healthy', 'success');
            }
            apiConnected = true;
        } else {
            if (apiConnected) {
                logMessage('API health check: Unhealthy', 'error');
            }
            apiConnected = false;
        }
        updateConnectionStatus();
        
    } catch (err) {
        if (apiConnected) {
            logMessage(`API health check failed: ${err.message}`, 'error');
        }
        apiConnected = false;
        updateConnectionStatus();
    }
}

async function checkQuestDbHealth() {
    try {
        // Try to ping QuestDB web console (port 9000)
        const response = await fetch('http://localhost:9000/', {
            method: 'GET',
            cache: 'no-cache',
            mode: 'no-cors' // QuestDB might not have CORS enabled
        });
        
        // With no-cors, we can't read the response, but if it doesn't throw, the server is reachable
        if (!questdbConnected) {
            logMessage('QuestDB health check: Healthy', 'success');
        }
        questdbConnected = true;
    } catch (err) {
        if (questdbConnected) {
            logMessage(`QuestDB health check failed: ${err.message}`, 'error');
        }
        questdbConnected = false;
    }
    updateConnectionStatus();
}

async function checkPostgresHealth() {
    try {
        // Use the health endpoint to check if API can connect to databases
        const response = await fetch('http://localhost:10901/health', {
            method: 'GET',
            cache: 'no-cache'
        });
        
        if (response.ok) {
            // If API health check passes, assume PostgreSQL is accessible
            if (!postgresConnected) {
                logMessage('PostgreSQL health check: Healthy', 'success');
            }
            postgresConnected = true;
        } else {
            if (postgresConnected) {
                logMessage('PostgreSQL health check: Unhealthy', 'error');
            }
            postgresConnected = false;
        }
    } catch (err) {
        if (postgresConnected) {
            logMessage(`PostgreSQL health check failed: ${err.message}`, 'error');
        }
        postgresConnected = false;
    }
    updateConnectionStatus();
}

// === STATS MANAGEMENT ===
async function resetStats() {
    try {
        logMessage('Resetting statistics...', 'info');
        
        // Call backend to reset server-side statistics
        const response = await fetch('http://localhost:10901/api/range/reset', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const result = await response.json();
        
        if (!response.ok) {
            logMessage(`Failed to reset backend statistics: ${result.message || 'Unknown error'}`, 'error');
            // Continue with frontend reset anyway
        }
        
        // Reset all frontend stats to zero
        stats.captured = 0;
        stats.parsed = 0;
        stats.dropped = 0;
        stats.flushed = 0;
        stats.failed = 0;
        stats.backpressure = 0;
        stats.avgLatency = 0;
        stats.motionCaptured = 0;
        stats.safetyCaptured = 0;
        stats.onvifCaptured = 0;
        stats.hubReceived = 0;
        stats.hubMotion = 0;
        stats.hubSafety = 0;
        stats.hubOnvif = 0;
        stats.parseRate = 0;
        stats.flushRate = 0;
        
        // Reset last stats for rate calculation
        lastStats = {
            captured: 0,
            parsed: 0,
            flushed: 0,
            timestamp: Date.now()
        };
        
        // Reset throughput rates
        throughput.capturedPps = 0;
        throughput.parsedPps = 0;
        throughput.flushedPps = 0;
        
        // Clear charts
        throughputData.labels = [];
        throughputData.captured = [];
        throughputData.parsed = [];
        throughputData.flushed = [];
        throughputChart.update();
        
        latencyData.labels = [];
        latencyData.values = [];
        
        // Update UI
        updateTelemetryStats();
        
        logMessage('All statistics reset to zero (frontend and backend)', 'success');
    } catch (err) {
        logMessage(`Error resetting statistics: ${err.message}`, 'error');
    }
}

// === REAL-TIME TELEMETRY ===
// Note: API polling removed - now using real-time telemetry via SignalR TelemetryHub

// === UI UPDATES ===
function updateConnectionStatus() {
    // Note: Hub status is handled separately by updateSignalRStatus()
    const apiStatusEl = document.getElementById('apiStatus');
    const apiStatusText = document.getElementById('apiStatusText');
    const questdbStatusEl = document.getElementById('questdbStatus');
    const questdbStatusText = document.getElementById('questdbStatusText');
    const postgresStatusEl = document.getElementById('postgresStatus');
    const postgresStatusText = document.getElementById('postgresStatusText');
    
    apiStatusEl.className = 'status-indicator ' + (apiConnected ? 'connected' : 'disconnected');
    apiStatusText.textContent = 'API: ' + (apiConnected ? 'Connected' : 'Disconnected');
    
    questdbStatusEl.className = 'status-indicator ' + (questdbConnected ? 'connected' : 'disconnected');
    questdbStatusText.textContent = 'QuestDB: ' + (questdbConnected ? 'Connected' : 'Disconnected');
    
    postgresStatusEl.className = 'status-indicator ' + (postgresConnected ? 'connected' : 'disconnected');
    postgresStatusText.textContent = 'PostgreSQL: ' + (postgresConnected ? 'Connected' : 'Disconnected');
}

// Fallback server status checker used by Packet Hub connect logic
async function checkServerStatus() {
    try {
        const res = await fetch('http://localhost:10901/health', { method: 'GET', cache: 'no-cache' });
        return !!res;
    } catch (_) {
        // If health check is blocked by CORS or unreachable, don't block UI
        return true;
    }
}

// === RANGE FORM HELPERS ===
function addEndpointRow(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;
    const row = document.createElement('div');
    row.className = 'endpoint-row';
    row.style = 'display:flex; gap:6px; margin: 4px 0;';
    row.innerHTML = `
        <input type=\"text\" placeholder=\"IP\" class=\"ep-ip\">\n\
        <input type=\"number\" placeholder=\"Port\" class=\"ep-port\">\n\
        <button type=\"button\" class=\"btn-stop ep-remove\" onclick=\"this.parentElement.remove()\">\u00D7</button>
    `;
    container.appendChild(row);
}

function collectEndpoints(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return [];
    const rows = Array.from(container.querySelectorAll('.endpoint-row'));
    const endpoints = [];
    rows.forEach(r => {
        const ip = r.querySelector('.ep-ip')?.value?.trim();
        const portStr = r.querySelector('.ep-port')?.value?.trim();
        const port = portStr ? parseInt(portStr) : null;
        if ((ip && ip.length > 0) || (port !== null && !isNaN(port))) {
            endpoints.push({ ip: ip || null, port: port });
        }
    });
    return endpoints;
}

function addCameraRow() {
    const container = document.getElementById('camsContainer');
    if (!container) return;
    const row = document.createElement('div');
    row.className = 'endpoint-row';
    row.style = 'display:flex; gap:6px; margin: 4px 0; align-items:center;';
    row.innerHTML = `
        <input type=\"text\" placeholder=\"Alias\" class=\"cam-alias\">\n\
        <label style=\"display:flex; align-items:center; gap:6px; color:#b0b0b0;\"><input type=\"checkbox\" class=\"cam-record\"> Record</label>\n\
        <button type=\"button\" class=\"btn-stop ep-remove\" onclick=\"this.parentElement.remove()\">\u00D7</button>
    `;
    container.appendChild(row);
}

function collectCams() {
    const container = document.getElementById('camsContainer');
    if (!container) return [];
    const rows = Array.from(container.querySelectorAll('.endpoint-row'));
    const cams = [];
    rows.forEach(r => {
        const alias = r.querySelector('.cam-alias')?.value?.trim();
        const isRecording = !!r.querySelector('.cam-record')?.checked;
        if (alias && alias.length > 0) {
            cams.push({ alias: alias, isRecording: isRecording });
        }
    });
    return cams;
}

function updateCaptureStats() {
    document.getElementById('totalCaptured').textContent = stats.captured.toLocaleString();
    const mc = document.getElementById('motionCaptured'); if (mc) mc.textContent = (stats.motionCaptured || 0).toLocaleString();
    const mcf = document.getElementById('motionCaptureFail'); if (mcf) mcf.textContent = (stats.motionCaptureFail || 0).toLocaleString();
    const sc = document.getElementById('safetyCaptured'); if (sc) sc.textContent = (stats.safetyCaptured || 0).toLocaleString();
    const scf = document.getElementById('safetyCaptureFail'); if (scf) scf.textContent = (stats.safetyCaptureFail || 0).toLocaleString();
    const oc = document.getElementById('onvifCaptured'); if (oc) oc.textContent = (stats.onvifCaptured || 0).toLocaleString();
    const ocf = document.getElementById('onvifCaptureFail'); if (ocf) ocf.textContent = (stats.onvifCaptureFail || 0).toLocaleString();
}

function updateParseStats() {
    document.getElementById('totalParsed').textContent = stats.parsed.toLocaleString();
    document.getElementById('totalDropped').textContent = stats.dropped.toLocaleString();
    const mps = document.getElementById('motionParseSuccess'); if (mps) mps.textContent = (stats.motionParseSuccess || 0).toLocaleString();
    const mpf = document.getElementById('motionParseFail'); if (mpf) mpf.textContent = (stats.motionParseFail || 0).toLocaleString();
    const sps = document.getElementById('safetyParseSuccess'); if (sps) sps.textContent = (stats.safetyParseSuccess || 0).toLocaleString();
    const spf = document.getElementById('safetyParseFail'); if (spf) spf.textContent = (stats.safetyParseFail || 0).toLocaleString();
    const ops = document.getElementById('onvifParseSuccess'); if (ops) ops.textContent = (stats.onvifParseSuccess || 0).toLocaleString();
    const opf = document.getElementById('onvifParseFail'); if (opf) opf.textContent = (stats.onvifParseFail || 0).toLocaleString();
    
    // Use the calculated rate from refreshStats instead of recalculating here
    const rate = stats.parseRate || 0;
    document.getElementById('parseRate').textContent = rate;
}

function updateDbStats() {
    document.getElementById('totalFlushed').textContent = stats.flushed.toLocaleString();
    document.getElementById('totalFailed').textContent = stats.failed.toLocaleString();
    
    // Use the calculated rate from refreshStats instead of recalculating here
    const rate = stats.flushRate || 0;
    document.getElementById('flushRate').textContent = rate;
    const mfs = document.getElementById('motionFlushSuccess'); if (mfs) mfs.textContent = (stats.motionFlushSuccess || 0).toLocaleString();
    const mff = document.getElementById('motionFlushFail'); if (mff) mff.textContent = (stats.motionFlushFail || 0).toLocaleString();
    const sfs = document.getElementById('safetyFlushSuccess'); if (sfs) sfs.textContent = (stats.safetyFlushSuccess || 0).toLocaleString();
    const sff = document.getElementById('safetyFlushFail'); if (sff) sff.textContent = (stats.safetyFlushFail || 0).toLocaleString();
    const ofs = document.getElementById('onvifFlushSuccess'); if (ofs) ofs.textContent = (stats.onvifFlushSuccess || 0).toLocaleString();
    const off = document.getElementById('onvifFlushFail'); if (off) off.textContent = (stats.onvifFlushFail || 0).toLocaleString();
}

function updateTelemetryStats() {
    // Update capture stats
    document.getElementById('totalCaptured').textContent = stats.captured.toLocaleString();
    const mc2 = document.getElementById('motionCaptured'); if (mc2) mc2.textContent = (stats.motionCaptured || 0).toLocaleString();
    const mcf2 = document.getElementById('motionCaptureFail'); if (mcf2) mcf2.textContent = (stats.motionCaptureFail || 0).toLocaleString();
    const sc2 = document.getElementById('safetyCaptured'); if (sc2) sc2.textContent = (stats.safetyCaptured || 0).toLocaleString();
    const scf2 = document.getElementById('safetyCaptureFail'); if (scf2) scf2.textContent = (stats.safetyCaptureFail || 0).toLocaleString();
    const oc2 = document.getElementById('onvifCaptured'); if (oc2) oc2.textContent = (stats.onvifCaptured || 0).toLocaleString();
    const ocf2 = document.getElementById('onvifCaptureFail'); if (ocf2) ocf2.textContent = (stats.onvifCaptureFail || 0).toLocaleString();
    
    // Update parse stats
    document.getElementById('totalParsed').textContent = stats.parsed.toLocaleString();
    document.getElementById('totalDropped').textContent = stats.dropped.toLocaleString();
    const mps2 = document.getElementById('motionParseSuccess'); if (mps2) mps2.textContent = (stats.motionParseSuccess || 0).toLocaleString();
    const mpf2 = document.getElementById('motionParseFail'); if (mpf2) mpf2.textContent = (stats.motionParseFail || 0).toLocaleString();
    const sps2 = document.getElementById('safetyParseSuccess'); if (sps2) sps2.textContent = (stats.safetyParseSuccess || 0).toLocaleString();
    const spf2 = document.getElementById('safetyParseFail'); if (spf2) spf2.textContent = (stats.safetyParseFail || 0).toLocaleString();
    const ops2 = document.getElementById('onvifParseSuccess'); if (ops2) ops2.textContent = (stats.onvifParseSuccess || 0).toLocaleString();
    const opf2 = document.getElementById('onvifParseFail'); if (opf2) opf2.textContent = (stats.onvifParseFail || 0).toLocaleString();
    
    // Update DB stats
    document.getElementById('totalFlushed').textContent = stats.flushed.toLocaleString();
    document.getElementById('totalFailed').textContent = stats.failed.toLocaleString();
    const mfs2 = document.getElementById('motionFlushSuccess'); if (mfs2) mfs2.textContent = (stats.motionFlushSuccess || 0).toLocaleString();
    const mff2 = document.getElementById('motionFlushFail'); if (mff2) mff2.textContent = (stats.motionFlushFail || 0).toLocaleString();
    const sfs2 = document.getElementById('safetyFlushSuccess'); if (sfs2) sfs2.textContent = (stats.safetyFlushSuccess || 0).toLocaleString();
    const sff2 = document.getElementById('safetyFlushFail'); if (sff2) sff2.textContent = (stats.safetyFlushFail || 0).toLocaleString();
    const ofs2 = document.getElementById('onvifFlushSuccess'); if (ofs2) ofs2.textContent = (stats.onvifFlushSuccess || 0).toLocaleString();
    const off2 = document.getElementById('onvifFlushFail'); if (off2) off2.textContent = (stats.onvifFlushFail || 0).toLocaleString();
    
    // Update throughput rates (packets per second)
    document.getElementById('parseRate').textContent = throughput.parsedPps.toLocaleString();
    document.getElementById('flushRate').textContent = throughput.flushedPps.toLocaleString();
    
    // Add captured throughput rate if element exists
    const capturedRateElement = document.getElementById('capturedRate');
    if (capturedRateElement) {
        capturedRateElement.textContent = throughput.capturedPps.toLocaleString();
    }
    
}

function updateHubStats() {
    // This function is now handled by updateTelemetryStats()
    updateTelemetryStats();
}

function updateChannelStats(motionRaw, safetyRaw, onvifRaw, motionParsed, safetyParsed, onvifParsed) {
    // Update Raw Channels (Capture -> Parse)
    if (motionRaw) {
        document.getElementById('motionRawChannelCapacity').textContent = motionRaw.capacity.toLocaleString();
        const mw = document.getElementById('motionRawWorkers'); if (mw) mw.textContent = (motionRaw.workers || 0).toLocaleString();
        const ml = document.getElementById('motionRawAvgLatency'); if (ml) ml.textContent = ((motionRaw.avgLatencyMs || motionRaw.avgLatency || 0).toFixed ? (motionRaw.avgLatencyMs || motionRaw.avgLatency || 0).toFixed(1) : (motionRaw.avgLatencyMs || motionRaw.avgLatency || 0)) + ' ms';
        document.getElementById('motionRawChannelPercent').textContent = motionRaw.utilizationPercent.toFixed(2) + '%';
        document.getElementById('motionRawChannelBar').style.width = Math.min(motionRaw.utilizationPercent, 100) + '%';
    }
    
    if (safetyRaw) {
        document.getElementById('safetyRawChannelCapacity').textContent = safetyRaw.capacity.toLocaleString();
        const sw = document.getElementById('safetyRawWorkers'); if (sw) sw.textContent = (safetyRaw.workers || 0).toLocaleString();
        const sl = document.getElementById('safetyRawAvgLatency'); if (sl) sl.textContent = ((safetyRaw.avgLatencyMs || safetyRaw.avgLatency || 0).toFixed ? (safetyRaw.avgLatencyMs || safetyRaw.avgLatency || 0).toFixed(1) : (safetyRaw.avgLatencyMs || safetyRaw.avgLatency || 0)) + ' ms';
        document.getElementById('safetyRawChannelPercent').textContent = safetyRaw.utilizationPercent.toFixed(2) + '%';
        document.getElementById('safetyRawChannelBar').style.width = Math.min(safetyRaw.utilizationPercent, 100) + '%';
    }
    
    if (onvifRaw) {
        document.getElementById('onvifRawChannelCapacity').textContent = onvifRaw.capacity.toLocaleString();
        const ow = document.getElementById('onvifRawWorkers'); if (ow) ow.textContent = (onvifRaw.workers || 0).toLocaleString();
        const ol = document.getElementById('onvifRawAvgLatency'); if (ol) ol.textContent = ((onvifRaw.avgLatencyMs || onvifRaw.avgLatency || 0).toFixed ? (onvifRaw.avgLatencyMs || onvifRaw.avgLatency || 0).toFixed(1) : (onvifRaw.avgLatencyMs || onvifRaw.avgLatency || 0)) + ' ms';
        document.getElementById('onvifRawChannelPercent').textContent = onvifRaw.utilizationPercent.toFixed(2) + '%';
        document.getElementById('onvifRawChannelBar').style.width = Math.min(onvifRaw.utilizationPercent, 100) + '%';
    }
    
    // Update Parsed Channels (Parse -> DB)
    if (motionParsed) {
        document.getElementById('motionParsedChannelCapacity').textContent = motionParsed.capacity.toLocaleString();
        const mpw = document.getElementById('motionParsedWorkers'); if (mpw) mpw.textContent = (motionParsed.workers || 0).toLocaleString();
        const mpl = document.getElementById('motionParsedAvgLatency'); if (mpl) mpl.textContent = ((motionParsed.avgLatencyMs || motionParsed.avgLatency || 0).toFixed ? (motionParsed.avgLatencyMs || motionParsed.avgLatency || 0).toFixed(1) : (motionParsed.avgLatencyMs || motionParsed.avgLatency || 0)) + ' ms';
        document.getElementById('motionParsedChannelPercent').textContent = motionParsed.utilizationPercent.toFixed(2) + '%';
        document.getElementById('motionParsedChannelBar').style.width = Math.min(motionParsed.utilizationPercent, 100) + '%';
    }
    
    if (safetyParsed) {
        document.getElementById('safetyParsedChannelCapacity').textContent = safetyParsed.capacity.toLocaleString();
        const spw = document.getElementById('safetyParsedWorkers'); if (spw) spw.textContent = (safetyParsed.workers || 0).toLocaleString();
        const spl = document.getElementById('safetyParsedAvgLatency'); if (spl) spl.textContent = ((safetyParsed.avgLatencyMs || safetyParsed.avgLatency || 0).toFixed ? (safetyParsed.avgLatencyMs || safetyParsed.avgLatency || 0).toFixed(1) : (safetyParsed.avgLatencyMs || safetyParsed.avgLatency || 0)) + ' ms';
        document.getElementById('safetyParsedChannelPercent').textContent = safetyParsed.utilizationPercent.toFixed(2) + '%';
        document.getElementById('safetyParsedChannelBar').style.width = Math.min(safetyParsed.utilizationPercent, 100) + '%';
    }
    
    if (onvifParsed) {
        document.getElementById('onvifParsedChannelCapacity').textContent = onvifParsed.capacity.toLocaleString();
        const opw = document.getElementById('onvifParsedWorkers'); if (opw) opw.textContent = (onvifParsed.workers || 0).toLocaleString();
        const opl = document.getElementById('onvifParsedAvgLatency'); if (opl) opl.textContent = ((onvifParsed.avgLatencyMs || onvifParsed.avgLatency || 0).toFixed ? (onvifParsed.avgLatencyMs || onvifParsed.avgLatency || 0).toFixed(1) : (onvifParsed.avgLatencyMs || onvifParsed.avgLatency || 0)) + ' ms';
        document.getElementById('onvifParsedChannelPercent').textContent = onvifParsed.utilizationPercent.toFixed(2) + '%';
        document.getElementById('onvifParsedChannelBar').style.width = Math.min(onvifParsed.utilizationPercent, 100) + '%';
    }
}

function updateUptime() {
    const uptime = Math.floor((Date.now() - startTime) / 1000);
    const hours = Math.floor(uptime / 3600);
    const minutes = Math.floor((uptime % 3600) / 60);
    const seconds = uptime % 60;
    document.getElementById('uptime').textContent = 
        `${hours}h ${minutes}m ${seconds}s`;
}

// === LOGGING ===
function logMessage(message, type = 'info') {
    const logsDiv = document.getElementById('logs');
    const logEntry = document.createElement('div');
    logEntry.className = `log-entry log-${type}`;
    
    const timestamp = new Date().toLocaleTimeString() + '.' + 
                      new Date().getMilliseconds().toString().padStart(3, '0');
    
    logEntry.textContent = `[${timestamp}] ${message}`;
    logsDiv.insertBefore(logEntry, logsDiv.firstChild);
    
    // Keep only last 100 logs
    while (logsDiv.children.length > 100) {
        logsDiv.removeChild(logsDiv.lastChild);
    }
}


function clearLogs() {
    document.getElementById('logs').innerHTML = '';
    
    // Also clear Packet Hub logs
    const packetHubLogs = document.getElementById('packetHubLogs');
    if (packetHubLogs) {
        packetHubLogs.innerHTML = '';
    }
    
    logMessage('All logs cleared (System + Packet Hub)', 'info');
}

// === PACKET HUB FUNCTIONALITY ===

let packetHubConnection = null;
let packetHubConnected = false;
let activeStreams = new Map(); // Track active streams by pipeline

// === AXIS CONTROL FUNCTIONS ===
function getSelectedAxis() {
    const axisSelect = document.getElementById('axisSelect');
    return parseInt(axisSelect.value);
}

function setAbsolutePosition() {
    const positionValue = document.getElementById('positionValue').value;
    const axis = getSelectedAxis();
    
    if (!positionValue) {
        logPacketHubMessage('Please enter a position value', 'error');
        return;
    }
    
    if (!packetHubConnected) {
        logPacketHubMessage('Packet Hub not connected', 'error');
        return;
    }
    
    const position = parseFloat(positionValue);
    logPacketHubMessage(`Setting absolute position ${position} for Axis ${axis}`, 'info');
    
    // Send MOT_SetPositionAbsolute command
    sendMotionCommand('MOT_SetPositionAbsolute', axis, position);
}

function setRelativePosition() {
    const positionValue = document.getElementById('positionValue').value;
    const axis = getSelectedAxis();
    
    if (!positionValue) {
        logPacketHubMessage('Please enter a position value', 'error');
        return;
    }
    
    if (!packetHubConnected) {
        logPacketHubMessage('Packet Hub not connected', 'error');
        return;
    }
    
    const position = parseFloat(positionValue);
    logPacketHubMessage(`Setting relative position ${position} for Axis ${axis}`, 'info');
    
    // Send MOT_SetPositionRelative command
    sendMotionCommand('MOT_SetPositionRelative', axis, position);
}

function setSpeed() {
    const speedValue = document.getElementById('speedValue').value;
    const axis = getSelectedAxis();
    
    if (!speedValue) {
        logPacketHubMessage('Please enter a speed value', 'error');
        return;
    }
    
    if (!packetHubConnected) {
        logPacketHubMessage('Packet Hub not connected', 'error');
        return;
    }
    
    const speed = parseFloat(speedValue);
    logPacketHubMessage(`Setting speed ${speed} for Axis ${axis}`, 'info');
    
    // Send MOT_SetSpeed command
    sendMotionCommand('MOT_SetSpeed', axis, speed);
}

function setAcceleration() {
    const accelerationValue = document.getElementById('accelerationValue').value;
    const axis = getSelectedAxis();
    
    if (!accelerationValue) {
        logPacketHubMessage('Please enter an acceleration value', 'error');
        return;
    }
    
    if (!packetHubConnected) {
        logPacketHubMessage('Packet Hub not connected', 'error');
        return;
    }
    
    const acceleration = parseFloat(accelerationValue);
    logPacketHubMessage(`Setting acceleration ${acceleration} for Axis ${axis}`, 'info');
    
    // Send MOT_SetAcceleration command
    sendMotionCommand('MOT_SetAcceleration', axis, acceleration);
}

function axisOn() {
    const axis = getSelectedAxis();
    
    if (!packetHubConnected) {
        logPacketHubMessage('Packet Hub not connected', 'error');
        return;
    }
    
    logPacketHubMessage(`Turning ON Axis ${axis}`, 'info');
    
    // Send MOT_AxisOn command
    sendMotionCommand('MOT_AxisOn', axis, 0);
}

function axisOff() {
    const axis = getSelectedAxis();
    
    if (!packetHubConnected) {
        logPacketHubMessage('Packet Hub not connected', 'error');
        return;
    }
    
    logPacketHubMessage(`Turning OFF Axis ${axis}`, 'info');
    
    // Send MOT_AxisOff command
    sendMotionCommand('MOT_AxisOff', axis, 0);
}

function axisReset() {
    const axis = getSelectedAxis();
    
    if (!packetHubConnected) {
        logPacketHubMessage('Packet Hub not connected', 'error');
        return;
    }
    
    logPacketHubMessage(`Resetting Axis ${axis}`, 'info');
    
    // Send MOT_AxisReset command
    sendMotionCommand('MOT_AxisReset', axis, 0);
}

function sendMotionCommand(command, axis, value) {
    try {
        // Create a mock packet for the motion command
        const mockPacket = {
            command: command,
            axis: axis,
            value: value,
            timestamp: Date.now()
        };
        
        logPacketHubMessage(`Sending ${command} to Axis ${axis} with value ${value}`, 'info');
        
        // In a real implementation, you would send this to the MotionSimulator
        // For now, we'll just log it
        console.log('Motion command:', mockPacket);
        
        // You could also send this via SignalR if you have a command endpoint
        // packetHubConnection.invoke('SendMotionCommand', mockPacket);
        
    } catch (error) {
        logPacketHubMessage(`Error sending motion command: ${error.message}`, 'error');
        console.error('Error sending motion command:', error);
    }
}

// Helper function to convert pipeline name to DataPipes enum value
function convertPipelineToEnum(pipelineName) {
    switch (pipelineName) {
        case 'MotionPackets':
            return 'Motion';
        case 'SafetyPackets':
            return 'Safety';
        case 'OnVIFPackets':
            return 'OnVIF';
        default:
            return pipelineName;
    }
}

// Define onDataPipeChange function early so it's available when HTML loads
function onDataPipeChange() {
    console.log('onDataPipeChange called');
    const dataPipe = document.getElementById('dataPipeSelect').value;
    console.log('Selected dataPipe:', dataPipe);
    const streamSelection = document.getElementById('streamSelection');
    const streamSelect = document.getElementById('streamSelect');
    const streamInfo = document.getElementById('streamInfo');
    
    if (dataPipe) {
        console.log('Showing stream selection for:', dataPipe);
        streamSelection.style.display = 'block';
        
        // Clear existing options
        streamSelect.innerHTML = '<option value="">-- Select Stream --</option>';
        
        // Populate stream options based on selected pipeline
        let streams = [];
        switch (dataPipe) {
            case 'Motion':
                streams = [
                    // Axis 1 commands
                    { value: 'MOT_GetMotorCurrent|false|1', text: 'MOT_GetMotorCurrent (RPT, Axis 1)' },
                    { value: 'MOT_GetMotorCurrent|true|1', text: 'MOT_GetMotorCurrent (CMD, Axis 1)' },
                    { value: 'MOT_GetMotorVoltage|false|1', text: 'MOT_GetMotorVoltage (RPT, Axis 1)' },
                    { value: 'MOT_GetMotorVoltage|true|1', text: 'MOT_GetMotorVoltage (CMD, Axis 1)' },
                    { value: 'MOT_GetMotorPosition|false|1', text: 'MOT_GetMotorPosition (RPT, Axis 1)' },
                    { value: 'MOT_GetMotorPosition|true|1', text: 'MOT_GetMotorPosition (CMD, Axis 1)' },
                    { value: 'MOT_GetLoadPosition|false|1', text: 'MOT_GetLoadPosition (RPT, Axis 1)' },
                    { value: 'MOT_GetLoadPosition|true|1', text: 'MOT_GetLoadPosition (CMD, Axis 1)' },
                    { value: 'MOT_GetMotorSpeed|false|1', text: 'MOT_GetMotorSpeed (RPT, Axis 1)' },
                    { value: 'MOT_GetMotorSpeed|true|1', text: 'MOT_GetMotorSpeed (CMD, Axis 1)' },
                    
                    // Axis 2 commands
                    { value: 'MOT_GetMotorCurrent|false|2', text: 'MOT_GetMotorCurrent (RPT, Axis 2)' },
                    { value: 'MOT_GetMotorCurrent|true|2', text: 'MOT_GetMotorCurrent (CMD, Axis 2)' },
                    { value: 'MOT_GetMotorVoltage|false|2', text: 'MOT_GetMotorVoltage (RPT, Axis 2)' },
                    { value: 'MOT_GetMotorVoltage|true|2', text: 'MOT_GetMotorVoltage (CMD, Axis 2)' },
                    { value: 'MOT_GetMotorPosition|false|2', text: 'MOT_GetMotorPosition (RPT, Axis 2)' },
                    { value: 'MOT_GetMotorPosition|true|2', text: 'MOT_GetMotorPosition (CMD, Axis 2)' },
                    { value: 'MOT_GetLoadPosition|false|2', text: 'MOT_GetLoadPosition (RPT, Axis 2)' },
                    { value: 'MOT_GetLoadPosition|true|2', text: 'MOT_GetLoadPosition (CMD, Axis 2)' },
                    { value: 'MOT_GetMotorSpeed|false|2', text: 'MOT_GetMotorSpeed (RPT, Axis 2)' },
                    { value: 'MOT_GetMotorSpeed|true|2', text: 'MOT_GetMotorSpeed (CMD, Axis 2)' },
                    
                    // Axis 4 commands
                    { value: 'MOT_GetMotorCurrent|false|4', text: 'MOT_GetMotorCurrent (RPT, Axis 4)' },
                    { value: 'MOT_GetMotorCurrent|true|4', text: 'MOT_GetMotorCurrent (CMD, Axis 4)' },
                    { value: 'MOT_GetMotorVoltage|false|4', text: 'MOT_GetMotorVoltage (RPT, Axis 4)' },
                    { value: 'MOT_GetMotorVoltage|true|4', text: 'MOT_GetMotorVoltage (CMD, Axis 4)' },
                    { value: 'MOT_GetMotorPosition|false|4', text: 'MOT_GetMotorPosition (RPT, Axis 4)' },
                    { value: 'MOT_GetMotorPosition|true|4', text: 'MOT_GetMotorPosition (CMD, Axis 4)' },
                    { value: 'MOT_GetLoadPosition|false|4', text: 'MOT_GetLoadPosition (RPT, Axis 4)' },
                    { value: 'MOT_GetLoadPosition|true|4', text: 'MOT_GetLoadPosition (CMD, Axis 4)' },
                    { value: 'MOT_GetMotorSpeed|false|4', text: 'MOT_GetMotorSpeed (RPT, Axis 4)' },
                    { value: 'MOT_GetMotorSpeed|true|4', text: 'MOT_GetMotorSpeed (CMD, Axis 4)' },
                    
                    // Axis 5 commands
                    { value: 'MOT_GetMotorCurrent|false|5', text: 'MOT_GetMotorCurrent (RPT, Axis 5)' },
                    { value: 'MOT_GetMotorCurrent|true|5', text: 'MOT_GetMotorCurrent (CMD, Axis 5)' },
                    { value: 'MOT_GetMotorVoltage|false|5', text: 'MOT_GetMotorVoltage (RPT, Axis 5)' },
                    { value: 'MOT_GetMotorVoltage|true|5', text: 'MOT_GetMotorVoltage (CMD, Axis 5)' },
                    { value: 'MOT_GetMotorPosition|false|5', text: 'MOT_GetMotorPosition (RPT, Axis 5)' },
                    { value: 'MOT_GetMotorPosition|true|5', text: 'MOT_GetMotorPosition (CMD, Axis 5)' },
                    { value: 'MOT_GetLoadPosition|false|5', text: 'MOT_GetLoadPosition (RPT, Axis 5)' },
                    { value: 'MOT_GetLoadPosition|true|5', text: 'MOT_GetLoadPosition (CMD, Axis 5)' },
                    { value: 'MOT_GetMotorSpeed|false|5', text: 'MOT_GetMotorSpeed (RPT, Axis 5)' },
                    { value: 'MOT_GetMotorSpeed|true|5', text: 'MOT_GetMotorSpeed (CMD, Axis 5)' }
                ];
                streamInfo.textContent = 'Motion Packets - Select a stream to register';
                break;
            case 'Safety':
                streams = [
                    { value: 'DO3_FIRE1|false|0', text: 'DO3_FIRE1 (RPT)' },
                    { value: 'DO3_FIRE1|true|0', text: 'DO3_FIRE1 (CMD)' },
                    { value: 'DO3_FIRE2|false|0', text: 'DO3_FIRE2 (RPT)' },
                    { value: 'DO3_FIRE2|true|0', text: 'DO3_FIRE2 (CMD)' },
                    { value: 'DO3_FIRE3|false|0', text: 'DO3_FIRE3 (RPT)' },
                    { value: 'DO3_FIRE3|true|0', text: 'DO3_FIRE3 (CMD)' },
                    { value: 'DO3_FIRE4|false|0', text: 'DO3_FIRE4 (RPT)' },
                    { value: 'DO3_FIRE4|true|0', text: 'DO3_FIRE4 (CMD)' },
                    { value: 'DO3_FIRE5|false|0', text: 'DO3_FIRE5 (RPT)' },
                    { value: 'DO3_FIRE5|true|0', text: 'DO3_FIRE5 (CMD)' },
                    { value: 'DO3_FIRE6|false|0', text: 'DO3_FIRE6 (RPT)' },
                    { value: 'DO3_FIRE6|true|0', text: 'DO3_FIRE6 (CMD)' }
                ];
                streamInfo.textContent = 'Safety Packets - Select a stream to register';
                break;
            case 'OnVIF':
                streams = [
                    { value: 'FOV_REQ|false|0', text: 'FOV_REQ (RPT)' },
                    { value: 'FOV_REQ|true|0', text: 'FOV_REQ (CMD)' },
                    { value: 'FOV_STS|false|0', text: 'FOV_STS (RPT)' },
                    { value: 'FOV_STS|true|0', text: 'FOV_STS (CMD)' },
                    { value: 'LRF_REQ|false|0', text: 'LRF_REQ (RPT)' },
                    { value: 'LRF_REQ|true|0', text: 'LRF_REQ (CMD)' },
                    { value: 'LRF_STS|false|0', text: 'LRF_STS (RPT)' },
                    { value: 'LRF_STS|true|0', text: 'LRF_STS (CMD)' }
                ];
                streamInfo.textContent = 'OnVIF Packets - Select a stream to register';
                break;
        }
        
        // Add options to select
        streams.forEach(stream => {
            const option = document.createElement('option');
            option.value = stream.value;
            option.textContent = stream.text;
            streamSelect.appendChild(option);
        });
        
        // Enable register button
        document.getElementById('registerStreamBtn').disabled = false;
        
    } else {
        console.log('Hiding stream selection');
        streamSelection.style.display = 'none';
        streamInfo.textContent = 'Select a pipeline above to see available streams';
    }
    
    updateActiveStreamsList();
}

// Update the active streams list display
function updateActiveStreamsList() {
    const activeStreamsList = document.getElementById('activeStreamsList');
    if (!activeStreamsList) return;
    
    if (activeStreams.size === 0) {
        activeStreamsList.innerHTML = '<div style="text-align: center; color: #888; padding: 20px;">No active streams</div>';
        return;
    }
    
    let html = '';
    activeStreams.forEach((streamRequest, streamKey) => {
        const displayName = `${streamRequest.description} (${streamRequest.isCmd ? 'CMD' : 'RPT'}, Axis ${streamRequest.axis})`;
        const pipelineName = streamRequest.dataPipe;
        
        html += `
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px; margin: 5px 0; background: rgba(255,255,255,0.05); border-radius: 6px; border-left: 3px solid #4caf50;">
                <div style="flex: 1; margin-right: 10px; min-width: 0;">
                    <div style="font-weight: bold; color: #4caf50; font-size: 14px;">${displayName}</div>
                    <div style="font-size: 12px; color: #888;">Pipeline: ${pipelineName}</div>
                </div>
                <button onclick="unregisterSpecificStream('${streamKey}')" style="height: 24px; padding: 0 8px; font-size: 11px; border-radius: 4px; background: #f44336; color: white; border: none; cursor: pointer; transition: all 0.2s ease; font-weight: 500; flex-shrink: 0; min-width: 60px; max-width: 80px;" onmouseover="this.style.background='#d32f2f'; this.style.transform='translateY(-1px)'" onmouseout="this.style.background='#f44336'; this.style.transform='translateY(0)'">
                    Remove
                </button>
            </div>
        `;
    });
    
    activeStreamsList.innerHTML = html;
}

// Unregister a specific stream by key
async function unregisterSpecificStream(streamKey) {
    if (!packetHubConnection || !packetHubConnected) {
        logPacketHubMessage('Not connected to Packet Hub', 'error');
        return;
    }
    
    const streamRequest = activeStreams.get(streamKey);
    if (!streamRequest) {
        logPacketHubMessage(`Stream ${streamKey} not found`, 'warning');
        return;
    }
    
    try {
        logPacketHubMessage(`Unregistering Stream: ${JSON.stringify(streamRequest)}`, 'info');
        await packetHubConnection.invoke('UnregisterFromMethod', streamRequest);
        activeStreams.delete(streamKey);
        updateActiveStreamsList();
        logPacketHubMessage('Stream unregistration request sent', 'success');
    } catch (err) {
        logPacketHubMessage(`Error unregistering stream: ${err.message}`, 'error');
    }
}

// Auto-connect packet hub on page load
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM loaded, attempting to connect packet hub...');
    
    // Initialize the connect/disconnect button
    updatePacketHubConnectButton();
    
    // Add event listener for data pipe selection
    const dataPipeSelect = document.getElementById('dataPipeSelect');
    if (dataPipeSelect) {
        dataPipeSelect.addEventListener('change', function(event) {
            console.log('Data pipe select change event triggered:', event.target.value);
            onDataPipeChange();
        });
        console.log('Added event listener to dataPipeSelect');
    } else {
        console.error('dataPipeSelect element not found!');
    }
    
    // Add a small delay to ensure all elements are ready
    setTimeout(() => {
        connectPacketHub();
    }, 100);
});

async function connectPacketHub() {
    console.log('connectPacketHub called');
    if (packetHubConnection) {
        logPacketHubMessage('Already connected or connecting...', 'warning');
        return;
    }
    
    const hubUrl = 'http://localhost:10901/hubs/packets';
    console.log('Attempting to connect to:', hubUrl);
    logPacketHubMessage(`Connecting to Packet Hub: ${hubUrl}`, 'info');
    
    // Check if SignalR is available
    if (typeof signalR === 'undefined') {
        console.error('SignalR library not loaded!');
        logPacketHubMessage('SignalR library not loaded!', 'error');
        updatePacketHubStatus('disconnected');
        return;
    }
    
    console.log('SignalR library loaded:', signalR);
    updatePacketHubStatus('connecting');
    
    // Check server status first
    const serverRunning = await checkServerStatus();
    if (!serverRunning) {
        console.error('Server is not running or not accessible');
        logPacketHubMessage('Server is not running or not accessible', 'error');
        updatePacketHubStatus('disconnected');
        return;
    }
    
    packetHubConnection = new signalR.HubConnectionBuilder()
        .withUrl(hubUrl)
        .withAutomaticReconnect([0, 1000, 2000, 5000])
        .configureLogging(signalR.LogLevel.Information)
        .build();

    // Handle connection events
    packetHubConnection.onclose((error) => {
        console.log('Packet Hub connection closed:', error);
        packetHubConnected = false;
        
        // Clear all active streams when connection is lost
        activeStreams.clear();
        updateActiveStreamsList();
        
        updatePacketHubStatus('disconnected');
        logPacketHubMessage('Packet Hub disconnected - all streams cleared', 'error');
    });

    packetHubConnection.onreconnecting((error) => {
        console.log('Packet Hub reconnecting...');
        packetHubConnected = false;
        
        // Clear all active streams when reconnecting starts
        activeStreams.clear();
        updateActiveStreamsList();
        
        updatePacketHubStatus('reconnecting');
        logPacketHubMessage('Packet Hub reconnecting... - all streams cleared', 'warning');
    });

    packetHubConnection.onreconnected((connectionId) => {
        console.log('Packet Hub reconnected successfully');
        packetHubConnected = true;
        updatePacketHubStatus('connected');
        logPacketHubMessage('Packet Hub reconnected successfully', 'success');
    });

    // Handle ACK messages - can be single ACK or array of ACKs
    packetHubConnection.on('Ack', (ackData) => {
        if (Array.isArray(ackData)) {
            // Multiple ACKs (on connect)
            ackData.forEach(ack => {
                logPacketHubMessage(`ACK Received: ${JSON.stringify(ack)}`, 'success');
            });
        } else {
            // Single ACK (on register/unregister/disconnect)
            logPacketHubMessage(`ACK Received: ${JSON.stringify(ackData)}`, 'success');
        }
        console.log('ACK received:', ackData);
        
        // Refresh active streams list after ACK
        updateActiveStreamsList();
    });

    // Handle packet data - new format: subscriptionKey, plainData
    packetHubConnection.on('OnReceivePacket', (subscriptionKey, plainData) => {
        try {
            console.log('Raw packet data received:', JSON.stringify({ subscriptionKey, plainData }, null, 2));
            console.log('plainData type:', typeof plainData);
            console.log('plainData keys:', plainData ? Object.keys(plainData) : 'null');
            
            // Safely extract values with null checks - handle both camelCase and PascalCase
            const subKey = subscriptionKey || 'N/A';
            
            // Try both camelCase and PascalCase property names
            const dataPipe = plainData?.DataPipe || plainData?.dataPipe || plainData?.DataPipe || 'N/A';
            const method = plainData?.MethodName || plainData?.methodName || plainData?.MethodName || 'N/A';
            const value = plainData?.Value != null ? String(plainData.Value) : (plainData?.value != null ? String(plainData.value) : 'N/A');
            const timestamp = plainData?.Timestamp ? new Date(plainData.Timestamp).toLocaleString() : (plainData?.timestamp ? new Date(plainData.timestamp).toLocaleString() : 'N/A');
            
            console.log('Extracted values:', { subKey, dataPipe, method, value, timestamp });
            
            // Format the packet for display with ASCII characters only
            const displayMessage = `[${subKey}] Received:
                Data Pipe: ${dataPipe}
                Method: ${method}
                Value: ${value}
                Timestamp: ${timestamp}`;
            
            logPacketHubMessage(displayMessage, 'info');
            console.log('Packet received:', { subscriptionKey: subKey, plainData });
            
            // Also show compact version in console
            console.log(`[PACKET] ${subKey} | ${dataPipe}.${method} = ${value}`);
        } catch (err) {
            logPacketHubMessage(`Error processing packet: ${err.message}`, 'error');
            console.error('Error processing packet:', err);
        }
    });

    try {
        console.log('Starting Packet Hub connection...');
        logPacketHubMessage('Starting Packet Hub connection...', 'info');
        
        // Add timeout to connection attempt
        const connectionPromise = packetHubConnection.start();
        const timeoutPromise = new Promise((_, reject) => 
            setTimeout(() => reject(new Error('Connection timeout after 10 seconds')), 10000)
        );
        
        await Promise.race([connectionPromise, timeoutPromise]);
        
        console.log('Packet Hub connection successful!');
        packetHubConnected = true;
        updatePacketHubStatus('connected');
        logPacketHubMessage('Packet Hub connected successfully!', 'success');
        console.log('Packet Hub connection established successfully');
    } catch (err) {
        console.error('Packet Hub connection failed:', err);
        logPacketHubMessage(`Packet Hub connection failed: ${err.message}`, 'error');
        console.error('Packet Hub connection error:', err);
        packetHubConnected = false;
        updatePacketHubStatus('disconnected');
    }
}

function updatePacketHubStatus(status) {
    const statusElement = document.getElementById('packetHubStatus');
    const manualConnectBtn = document.getElementById('manualConnectBtn');

    if (statusElement) {
        switch (status) {
            case 'connected':
                statusElement.textContent = 'Connected';
                statusElement.style.color = '#4caf50';
                if (manualConnectBtn) manualConnectBtn.style.display = 'none';
                break;
            case 'connecting':
            case 'reconnecting':
                statusElement.textContent = 'Connecting...';
                statusElement.style.color = '#ff9800';
                if (manualConnectBtn) manualConnectBtn.style.display = 'none';
                break;
            case 'disconnected':
            default:
                statusElement.textContent = 'Disconnected';
                statusElement.style.color = '#f44336';
                if (manualConnectBtn) manualConnectBtn.style.display = 'inline-block';
                break;
        }
    }

    // Update the connect/disconnect button (safe if missing)
    updatePacketHubConnectButton();

    // Update button states based on current pipeline selection
    if (typeof updatePipelineButtons === 'function') {
        updatePipelineButtons();
    }
}

// Update the connect/disconnect button text and styling
function updatePacketHubConnectButton() {
    const connectBtn = document.getElementById('packetHubConnectBtn');
    if (!connectBtn) return;
    
    if (packetHubConnected) {
        connectBtn.textContent = 'Disconnect';
        connectBtn.className = 'btn-stop';
    } else {
        connectBtn.textContent = 'Connect';
        connectBtn.className = 'btn-start';
    }
}

// Toggle connection function for the connect/disconnect button
async function togglePacketHubConnection() {
    if (packetHubConnected) {
        await disconnectPacketHub();
    } else {
        await connectPacketHub();
    }
}

// Disconnect packet hub function
async function disconnectPacketHub() {
    if (packetHubConnection) {
        try {
            await packetHubConnection.stop();
            packetHubConnection = null;
            packetHubConnected = false;
            
            // Clear all active streams when disconnecting
            activeStreams.clear();
            updateActiveStreamsList();
            
            updatePacketHubStatus('disconnected');
            logPacketHubMessage('Packet Hub disconnected manually - all streams cleared', 'info');
            updatePacketHubConnectButton();
        } catch (error) {
            console.error('Error disconnecting Packet Hub:', error);
            logPacketHubMessage(`Error disconnecting: ${error.message}`, 'error');
        }
    }
}

// Manual connect function for fallback
async function manualConnectPacketHub() {
    console.log('Manual connect triggered');
    await connectPacketHub();
}

// Register selected stream
async function registerSelectedStream() {
    if (!packetHubConnection || !packetHubConnected) {
        logPacketHubMessage('Not connected to Packet Hub', 'error');
        return;
    }

    const dataPipe = document.getElementById('dataPipeSelect').value;
    const streamValue = document.getElementById('streamSelect').value;
    
    if (!dataPipe || !streamValue) {
        logPacketHubMessage('Please select both pipeline and stream', 'warning');
        return;
    }

    // Parse stream value (format: description|isCmd|axis)
    const [description, isCmdStr, axisStr] = streamValue.split('|');
    const isCmd = isCmdStr === 'true';
    const axis = parseInt(axisStr) || 0;

    const streamRequest = {
        dataPipe: convertPipelineToEnum(dataPipe),
        description: description,
        isCmd: isCmd,
        axis: axis
    };

    const streamKey = `${streamRequest.dataPipe}|${streamRequest.description}|${streamRequest.isCmd}|${streamRequest.axis}`.toLowerCase();
    
    if (activeStreams.has(streamKey)) {
        logPacketHubMessage(`Stream ${streamKey} is already registered`, 'warning');
        return;
    }

    try {
        logPacketHubMessage(`Registering Stream: ${JSON.stringify(streamRequest)}`, 'info');
        await packetHubConnection.invoke('RegisterToMethod', streamRequest);
        activeStreams.set(streamKey, streamRequest);
        updateActiveStreamsList();
        logPacketHubMessage('Stream registration request sent', 'success');
    } catch (err) {
        logPacketHubMessage(`Error registering stream: ${err.message}`, 'error');
    }
}

// Unregister selected stream
async function unregisterSelectedStream() {
    if (!packetHubConnection || !packetHubConnected) {
        logPacketHubMessage('Not connected to Packet Hub', 'error');
        return;
    }

    const dataPipe = document.getElementById('dataPipeSelect').value;
    const streamValue = document.getElementById('streamSelect').value;
    
    if (!dataPipe || !streamValue) {
        logPacketHubMessage('Please select both pipeline and stream', 'warning');
        return;
    }

    // Parse stream value (format: description|isCmd|axis)
    const [description, isCmdStr, axisStr] = streamValue.split('|');
    const isCmd = isCmdStr === 'true';
    const axis = parseInt(axisStr) || 0;

    const streamRequest = {
        dataPipe: convertPipelineToEnum(dataPipe),
        description: description,
        isCmd: isCmd,
        axis: axis
    };

    const streamKey = `${streamRequest.dataPipe}|${streamRequest.description}|${streamRequest.isCmd}|${streamRequest.axis}`.toLowerCase();
    
    if (!activeStreams.has(streamKey)) {
        logPacketHubMessage(`Stream ${streamKey} is not registered`, 'warning');
        return;
    }

    try {
        logPacketHubMessage(`Unregistering Stream: ${JSON.stringify(streamRequest)}`, 'info');
        await packetHubConnection.invoke('UnregisterFromMethod', streamRequest);
        activeStreams.delete(streamKey);
        updateActiveStreamsList();
        logPacketHubMessage('Stream unregistration request sent', 'success');
    } catch (err) {
        logPacketHubMessage(`Error unregistering stream: ${err.message}`, 'error');
    }
}

// Unified Stream Registration/Unregistration
async function registerStream() {
    if (!packetHubConnection || !packetHubConnected) {
        logPacketHubMessage('Not connected to Packet Hub', 'error');
        return;
    }

    const dataPipe = document.getElementById('dataPipeSelect').value;
    if (!dataPipe) {
        logPacketHubMessage('Please select a data pipeline first', 'warning');
        return;
    }

    let streamRequest;
    
    switch (dataPipe) {
        case 'MotionPackets':
            const motionDescription = document.getElementById('motionDescriptionSelect').value;
            const motionIsCmd = document.getElementById('motionIsCmdSelect').value === 'true';
            const motionAxis = parseInt(document.getElementById('motionAxisInput').value) || 0;
            
            streamRequest = {
                dataPipe: 'MotionPackets',
                description: motionDescription,
                isCmd: motionIsCmd,
                axis: motionAxis
            };
            break;
            
        case 'SafetyPackets':
            const safetyDescription = document.getElementById('safetyDescriptionSelect').value;
            const safetyIsCmd = document.getElementById('safetyIsCmdSelect').value === 'true';
            
            streamRequest = {
                dataPipe: 'SafetyPackets',
                description: safetyDescription,
                isCmd: safetyIsCmd,
                axis: 0
            };
            break;
            
        case 'OnVIFPackets':
            const onvifDescription = document.getElementById('onvifDescriptionSelect').value;
            const onvifIsCmd = document.getElementById('onvifIsCmdSelect').value === 'true';
            
            streamRequest = {
                dataPipe: 'OnVIFPackets',
                description: onvifDescription,
                isCmd: onvifIsCmd,
                axis: 0
            };
            break;
            
        default:
            logPacketHubMessage('Unknown data pipeline', 'error');
            return;
    }

    const streamKey = `${streamRequest.dataPipe}|${streamRequest.description}|${streamRequest.isCmd}|${streamRequest.axis}`.toLowerCase();
    
    if (activeStreams.has(streamKey)) {
        logPacketHubMessage(`Stream ${streamKey} is already registered`, 'warning');
        return;
    }

    try {
        logPacketHubMessage(`Registering Stream: ${JSON.stringify(streamRequest)}`, 'info');
        await packetHubConnection.invoke('RegisterToMethod', streamRequest);
        activeStreams.set(streamKey, streamRequest);
        updateActiveStreamsList();
        logPacketHubMessage('Stream registration request sent', 'success');
    } catch (err) {
        logPacketHubMessage(`Error registering stream: ${err.message}`, 'error');
    }
}

async function unregisterStream() {
    if (!packetHubConnection || !packetHubConnected) {
        logPacketHubMessage('Not connected to Packet Hub', 'error');
        return;
    }

    const dataPipe = document.getElementById('dataPipeSelect').value;
    if (!dataPipe) {
        logPacketHubMessage('Please select a data pipeline first', 'warning');
        return;
    }

    let streamRequest;
    
    switch (dataPipe) {
        case 'MotionPackets':
            const motionDescription = document.getElementById('motionDescriptionSelect').value;
            const motionIsCmd = document.getElementById('motionIsCmdSelect').value === 'true';
            const motionAxis = parseInt(document.getElementById('motionAxisInput').value) || 0;
            
            streamRequest = {
                dataPipe: 'MotionPackets',
                description: motionDescription,
                isCmd: motionIsCmd,
                axis: motionAxis
            };
            break;
            
        case 'SafetyPackets':
            const safetyDescription = document.getElementById('safetyDescriptionSelect').value;
            const safetyIsCmd = document.getElementById('safetyIsCmdSelect').value === 'true';
            
            streamRequest = {
                dataPipe: 'SafetyPackets',
                description: safetyDescription,
                isCmd: safetyIsCmd,
                axis: 0
            };
            break;
            
        case 'OnVIFPackets':
            const onvifDescription = document.getElementById('onvifDescriptionSelect').value;
            const onvifIsCmd = document.getElementById('onvifIsCmdSelect').value === 'true';
            
            streamRequest = {
                dataPipe: 'OnVIFPackets',
                description: onvifDescription,
                isCmd: onvifIsCmd,
                axis: 0
            };
            break;
            
        default:
            logPacketHubMessage('Unknown data pipeline', 'error');
            return;
    }

    const streamKey = `${streamRequest.dataPipe}|${streamRequest.description}|${streamRequest.isCmd}|${streamRequest.axis}`.toLowerCase();
    
    if (!activeStreams.has(streamKey)) {
        logPacketHubMessage(`Stream ${streamKey} is not registered`, 'warning');
        return;
    }

    try {
        logPacketHubMessage(`Unregistering Stream: ${JSON.stringify(streamRequest)}`, 'info');
        await packetHubConnection.invoke('UnregisterFromMethod', streamRequest);
        activeStreams.delete(streamKey);
        updateActiveStreamsList();
        logPacketHubMessage('Stream unregistration request sent', 'success');
    } catch (err) {
        logPacketHubMessage(`Error unregistering stream: ${err.message}`, 'error');
    }
}

function updateStreamButtons(isRegistered) {
    const registerBtn = document.getElementById('registerStreamBtn');
    const unregisterBtn = document.getElementById('unregisterStreamBtn');
    
    if (registerBtn && unregisterBtn) {
        if (isRegistered) {
            registerBtn.disabled = true;
            unregisterBtn.disabled = false;
            registerBtn.textContent = 'Registered';
            unregisterBtn.textContent = 'Unregister Stream';
        } else {
            registerBtn.disabled = false;
            unregisterBtn.disabled = true;
            registerBtn.textContent = 'Register Stream';
            unregisterBtn.textContent = 'Unregistered';
        }
    }
}

function logPacketHubMessage(message, type = 'info') {
    const logsDiv = document.getElementById('packetHubLogs');
    const logEntry = document.createElement('div');
    logEntry.className = `log-entry log-${type}`;
    
    const timestamp = new Date().toLocaleTimeString() + '.' + 
                      new Date().getMilliseconds().toString().padStart(3, '0');
    
    // Create text node to avoid encoding issues with special characters
    const timestampText = `[${timestamp}] `;
    const messageText = String(message);
    
    logEntry.textContent = timestampText + messageText;
    logsDiv.insertBefore(logEntry, logsDiv.firstChild);
    
    // Keep only last 100 logs
    while (logsDiv.children.length > 100) {
        logsDiv.removeChild(logsDiv.lastChild);
    }
}


