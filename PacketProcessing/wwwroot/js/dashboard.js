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
    hubMotion: 0,
    hubSafety: 0,
    hubOnvif: 0,
    parseRate: 0,
    flushRate: 0
};

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

let throughputChart, latencyChart;

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
    setInterval(refreshStats, 2000);
    
    // Automatically connect to SignalR
    logMessage('Dashboard loaded. Connecting to SignalR automatically...', 'info');
    connectHub();
});

// === STATE MANAGEMENT ===
async function loadCurrentState() {
    try {
        const response = await fetch('http://localhost:10901/api/v1/range/mode');
        
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
    
    // Latency Chart
    const latencyCtx = document.getElementById('latencyChart').getContext('2d');
    latencyChart = new Chart(latencyCtx, {
        type: 'line',
        data: {
            labels: latencyData.labels,
            datasets: [{
                label: 'Latency (ms)',
                data: latencyData.values,
                borderColor: '#e91e63',
                backgroundColor: 'rgba(233, 30, 99, 0.1)',
                tension: 0.4,
                fill: true
            }]
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
    
    // Latency
    if (avgLatency > 0) {
        latencyData.labels.push(now);
        latencyData.values.push(avgLatency);
        
        if (latencyData.labels.length > 60) {
            latencyData.labels.shift();
            latencyData.values.shift();
        }
        
        latencyChart.update('none');
    }
}

// === SIGNALR HUB ===
// toggleSignalR function removed - SignalR now connects automatically

async function connectHub() {
    if (connection) {
        logMessage('Already connected or connecting...', 'warning');
        return;
    }
    
    const hubUrl = 'http://localhost:10901/hub/packets';
    logMessage(`Connecting to SignalR hub: ${hubUrl}`, 'info');
    
    // Show connecting state
    updateSignalRStatus();
    
    connection = new signalR.HubConnectionBuilder()
        .withUrl(hubUrl)
        .withAutomaticReconnect([0, 1000, 2000, 5000])
        .configureLogging(signalR.LogLevel.Information)
        .build();

    connection.on('OnReceive', (methodName, data) => {
        stats.hubReceived++;
        
        if (methodName === 'MotionPacketEntity') stats.hubMotion++;
        else if (methodName === 'SafetyPacketEntity') stats.hubSafety++;
        else if (methodName === 'OnVIFPacketEntity') stats.hubOnvif++;
        
        updateHubStats();
        
        // Log to SignalR packet log with full packet data
        logSignalRPacket(methodName, data);
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
    if (activeDevice) {
        titleEl.textContent = `Kanat Packet Processing - Telemetry Dashboard [${activeDevice}]`;
    } else {
        titleEl.textContent = 'Kanat Packet Processing - Telemetry Dashboard';
    }
}

// === DEVICE MANAGEMENT ===
async function loadAvailableDevices() {
    try {
        const response = await fetch('http://localhost:10901/api/v1/range/realtime/devices');
        
        if (!response.ok) {
            logMessage('Failed to load available devices', 'error');
            return;
        }
        
        const result = await response.json();
        const devices = result.data || result;
        
        const select = document.getElementById('deviceNameSelect');
        select.innerHTML = '';
        
        if (devices && devices.length > 0) {
            devices.forEach(device => {
                const option = document.createElement('option');
                option.value = device;
                option.textContent = device;
                select.appendChild(option);
            });
            logMessage(`Loaded ${devices.length} available network devices`, 'success');
        } else {
            const option = document.createElement('option');
            option.value = '';
            option.textContent = 'No devices available';
            select.appendChild(option);
            logMessage('No network devices found', 'warning');
        }
    } catch (err) {
        logMessage(`Error loading devices: ${err.message}`, 'error');
        const select = document.getElementById('deviceNameSelect');
        select.innerHTML = '<option value="">Error loading devices</option>';
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
        const response = await fetch(`http://localhost:10901/api/v1/range/mode/${mode}`, {
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
async function startCapture() {
    const deviceName = document.getElementById('deviceNameSelect').value.trim();
    
    if (!deviceName) {
        logMessage('Please enter a device name', 'error');
        return;
    }
    
    try {
        logMessage(`Starting capture on device: ${deviceName}...`, 'info');
        
        const response = await fetch(`http://localhost:10901/api/v1/range/realtime/start/${encodeURIComponent(deviceName)}`, {
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
            logMessage(`Capture started successfully on ${deviceName}`, 'success');
        } else {
            logMessage(`Failed to start capture: ${result.message || 'Unknown error'}`, 'error');
        }
    } catch (err) {
        logMessage(`Error starting capture: ${err.message}`, 'error');
    }
}

async function stopCapture() {
    try {
        logMessage('Stopping capture...', 'info');
        
        const response = await fetch('http://localhost:10901/api/v1/range/realtime/stop', {
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
        // PostgreSQL port 5432 is not HTTP, so we check if we can query through API
        // We'll use the status endpoint as a proxy since it queries the database
        const response = await fetch('http://localhost:10901/api/v1/range/status', {
            method: 'GET',
            cache: 'no-cache'
        });
        
        
        if (response.ok) {
            // If API can return stats, it means it can connect to databases
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
        const response = await fetch('http://localhost:10901/api/v1/range/reset', {
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
        
        // Clear charts
        throughputData.labels = [];
        throughputData.captured = [];
        throughputData.parsed = [];
        throughputData.flushed = [];
        throughputChart.update();
        
        latencyData.labels = [];
        latencyData.values = [];
        latencyChart.update();
        
        // Update UI
        updateCaptureStats();
        updateParseStats();
        updateDbStats();
        updateHubStats();
        
        logMessage('All statistics reset to zero (frontend and backend)', 'success');
    } catch (err) {
        logMessage(`Error resetting statistics: ${err.message}`, 'error');
    }
}

// === API POLLING ===
let lastStats = {
    captured: 0,
    parsed: 0,
    flushed: 0,
    timestamp: Date.now()
};

// Initialize stats properly on first load
let isFirstLoad = true;

async function refreshStats() {
    // Only refresh stats if API is healthy
    if (!apiConnected) {
        return;
    }
    
    try {
        const response = await fetch('http://localhost:10901/api/v1/range/status');
        
        if (!response.ok) {
            return;
        }
        
        const result = await response.json();
        
        // Extract data from ResponseResult wrapper
        const data = result.data || result;
        
        // Calculate deltas for rate
        const now = Date.now();
        const deltaTime = (now - lastStats.timestamp) / 1000; // seconds
        
        // Initialize deltas to 0
        let capturedDelta = 0;
        let parsedDelta = 0;
        let flushedDelta = 0;
        
        // Avoid division by zero and negative values, and handle first load
        if (deltaTime > 0 && !isFirstLoad) {
            capturedDelta = Math.max(0, Math.round((data.captured - lastStats.captured) / deltaTime));
            parsedDelta = Math.max(0, Math.round((data.parsed - lastStats.parsed) / deltaTime));
            flushedDelta = Math.max(0, Math.round((data.flushed - lastStats.flushed) / deltaTime));
            
            // Store calculated rates in stats object
            stats.parseRate = parsedDelta;
            stats.flushRate = flushedDelta;
        } else if (isFirstLoad) {
            // On first load, set rates to 0
            stats.parseRate = 0;
            stats.flushRate = 0;
            isFirstLoad = false;
        }
        
        lastStats = {
            captured: data.captured || 0,
            parsed: data.parsed || 0,
            flushed: data.flushed || 0,
            timestamp: now
        };
        
        // Update stats
        stats.captured = data.captured || 0;
        stats.parsed = data.parsed || 0;
        stats.dropped = data.dropped || 0;
        stats.flushed = data.flushed || 0;
        stats.failed = data.failed || 0;
        stats.backpressure = data.backpressure || 0;
        stats.avgLatency = data.avgLatency || 0;
        stats.motionCaptured = data.motionCaptured || 0;
        stats.safetyCaptured = data.safetyCaptured || 0;
        stats.onvifCaptured = data.onvifCaptured || 0;
        
        updateCaptureStats();
        updateParseStats();
        updateDbStats();
        
        // Debug: Log full data and channel data to console
        console.log('Full response data:', data);
        
        // Handle both PascalCase (C#) and camelCase (JavaScript) property names
        const motionRaw = data.motionRawChannel || data.MotionRawChannel;
        const safetyRaw = data.safetyRawChannel || data.SafetyRawChannel;
        const onvifRaw = data.onvifRawChannel || data.OnvifRawChannel;
        const motionParsed = data.motionParsedChannel || data.MotionParsedChannel;
        const safetyParsed = data.safetyParsedChannel || data.SafetyParsedChannel;
        const onvifParsed = data.onvifParsedChannel || data.OnvifParsedChannel;
        
        console.log('Channel data extracted:', {
            motionRaw, safetyRaw, onvifRaw,
            motionParsed, safetyParsed, onvifParsed
        });
        
        updateChannelStats(
            motionRaw, safetyRaw, onvifRaw,
            motionParsed, safetyParsed, onvifParsed
        );
        updateChart(capturedDelta, parsedDelta, flushedDelta, data.avgLatency || 0);
        
    } catch (err) {
        console.error('Failed to fetch stats:', err);
    }
}

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

function updateCaptureStats() {
    document.getElementById('totalCaptured').textContent = stats.captured.toLocaleString();
    document.getElementById('motionCaptured').textContent = (stats.motionCaptured || 0).toLocaleString();
    document.getElementById('safetyCaptured').textContent = (stats.safetyCaptured || 0).toLocaleString();
    document.getElementById('onvifCaptured').textContent = (stats.onvifCaptured || 0).toLocaleString();
}

function updateParseStats() {
    document.getElementById('totalParsed').textContent = stats.parsed.toLocaleString();
    document.getElementById('totalDropped').textContent = stats.dropped.toLocaleString();
    document.getElementById('backpressure').textContent = stats.backpressure.toLocaleString();
    
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
    
    const avgLatency = stats.avgLatency || 0;
    document.getElementById('avgLatency').textContent = avgLatency.toFixed(1);
}

function updateHubStats() {
    document.getElementById('hubPacketsReceived').textContent = stats.hubReceived.toLocaleString();
    document.getElementById('hubMotion').textContent = stats.hubMotion.toLocaleString();
    document.getElementById('hubSafety').textContent = stats.hubSafety.toLocaleString();
    document.getElementById('hubOnvif').textContent = stats.hubOnvif.toLocaleString();
}

function updateChannelStats(motionRaw, safetyRaw, onvifRaw, motionParsed, safetyParsed, onvifParsed) {
    // Update Raw Channels (Capture -> Parse)
    if (motionRaw) {
        document.getElementById('motionRawChannelCapacity').textContent = motionRaw.capacity.toLocaleString();
        document.getElementById('motionRawChannelSize').textContent = motionRaw.currentSize.toLocaleString();
        document.getElementById('motionRawChannelPercent').textContent = motionRaw.utilizationPercent.toFixed(2) + '%';
        document.getElementById('motionRawChannelBar').style.width = Math.min(motionRaw.utilizationPercent, 100) + '%';
    }
    
    if (safetyRaw) {
        document.getElementById('safetyRawChannelCapacity').textContent = safetyRaw.capacity.toLocaleString();
        document.getElementById('safetyRawChannelSize').textContent = safetyRaw.currentSize.toLocaleString();
        document.getElementById('safetyRawChannelPercent').textContent = safetyRaw.utilizationPercent.toFixed(2) + '%';
        document.getElementById('safetyRawChannelBar').style.width = Math.min(safetyRaw.utilizationPercent, 100) + '%';
    }
    
    if (onvifRaw) {
        document.getElementById('onvifRawChannelCapacity').textContent = onvifRaw.capacity.toLocaleString();
        document.getElementById('onvifRawChannelSize').textContent = onvifRaw.currentSize.toLocaleString();
        document.getElementById('onvifRawChannelPercent').textContent = onvifRaw.utilizationPercent.toFixed(2) + '%';
        document.getElementById('onvifRawChannelBar').style.width = Math.min(onvifRaw.utilizationPercent, 100) + '%';
    }
    
    // Update Parsed Channels (Parse -> DB)
    if (motionParsed) {
        document.getElementById('motionParsedChannelCapacity').textContent = motionParsed.capacity.toLocaleString();
        document.getElementById('motionParsedChannelSize').textContent = motionParsed.currentSize.toLocaleString();
        document.getElementById('motionParsedChannelPercent').textContent = motionParsed.utilizationPercent.toFixed(2) + '%';
        document.getElementById('motionParsedChannelBar').style.width = Math.min(motionParsed.utilizationPercent, 100) + '%';
    }
    
    if (safetyParsed) {
        document.getElementById('safetyParsedChannelCapacity').textContent = safetyParsed.capacity.toLocaleString();
        document.getElementById('safetyParsedChannelSize').textContent = safetyParsed.currentSize.toLocaleString();
        document.getElementById('safetyParsedChannelPercent').textContent = safetyParsed.utilizationPercent.toFixed(2) + '%';
        document.getElementById('safetyParsedChannelBar').style.width = Math.min(safetyParsed.utilizationPercent, 100) + '%';
    }
    
    if (onvifParsed) {
        document.getElementById('onvifParsedChannelCapacity').textContent = onvifParsed.capacity.toLocaleString();
        document.getElementById('onvifParsedChannelSize').textContent = onvifParsed.currentSize.toLocaleString();
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

function logSignalRPacket(packetType, data) {
    const signalrLogsDiv = document.getElementById('signalrLogs');
    const logEntry = document.createElement('div');
    logEntry.className = 'log-entry log-success';
    
    const timestamp = new Date().toLocaleTimeString() + '.' + 
                      new Date().getMilliseconds().toString().padStart(3, '0');
    
    // Format packet data nicely
    const packetInfo = JSON.stringify(data, null, 2);
    logEntry.innerHTML = `<strong>[${timestamp}] ${packetType}</strong><pre style="margin: 5px 0; padding: 5px; background: #2a2a2a; border-radius: 3px; font-size: 11px; overflow-x: auto;">${packetInfo}</pre>`;
    
    signalrLogsDiv.insertBefore(logEntry, signalrLogsDiv.firstChild);
    
    // Keep only last 50 SignalR packet logs
    while (signalrLogsDiv.children.length > 50) {
        signalrLogsDiv.removeChild(signalrLogsDiv.lastChild);
    }
    
    // Also log a simple summary to system logs
    const valueStr = data.value !== undefined ? data.value.toFixed(2) : 
                   data.Value !== undefined ? data.Value.toFixed(2) : 
                   'N/A';
    logMessage(`SignalR Packet: ${packetType} | Value: ${valueStr}`, 'success');
}

function clearLogs() {
    document.getElementById('logs').innerHTML = '';
    document.getElementById('signalrLogs').innerHTML = '';
    logMessage('All logs cleared', 'info');
}


