const API_BASE = 'http://localhost:5001/api';

let isRunning = false;

// DOM Elements
const fireBtn = document.getElementById('fireBtn');
const stopBtn = document.getElementById('stopBtn');
const clearBtn = document.getElementById('clearBtn');
const interfaceSelect = document.getElementById('interface');
const pcapSelect = document.getElementById('pcap');
const loopInput = document.getElementById('loop');
const ppsInput = document.getElementById('pps');
const outputBox = document.getElementById('output');
const statusText = document.getElementById('statusText');
const statusIndicator = document.getElementById('statusIndicator');

// Initialize
window.addEventListener('load', () => {
    loadInterfaces();
    loadPcaps();
    checkStatus();
    
    // Check status periodically
    setInterval(checkStatus, 2000);
});

// Event Listeners
fireBtn.addEventListener('click', startReplay);
stopBtn.addEventListener('click', stopReplay);
clearBtn.addEventListener('click', clearOutput);

// API Functions
async function loadInterfaces() {
    try {
        const response = await fetch(`${API_BASE}/interfaces`);
        const data = await response.json();
        
        if (data.success) {
            interfaceSelect.innerHTML = '';
            data.data.forEach(iface => {
                const option = document.createElement('option');
                option.value = iface;
                option.textContent = iface;
                interfaceSelect.appendChild(option);
            });
            
            if (data.data.length > 0) {
                interfaceSelect.value = data.data[0];
            }
        } else {
            appendOutput(`Error loading interfaces: ${data.error}\n`, 'error');
        }
    } catch (error) {
        appendOutput(`Failed to load interfaces: ${error.message}\n`, 'error');
        interfaceSelect.innerHTML = '<option value="">Error loading interfaces</option>';
    }
}

async function loadPcaps() {
    try {
        const response = await fetch(`${API_BASE}/pcaps`);
        const data = await response.json();
        
        if (data.success) {
            pcapSelect.innerHTML = '';
            if (data.data.length === 0) {
                pcapSelect.innerHTML = '<option value="">No PCAP files found</option>';
            } else {
                data.data.forEach(pcap => {
                    const option = document.createElement('option');
                    option.value = pcap;
                    option.textContent = pcap;
                    pcapSelect.appendChild(option);
                });
                
                pcapSelect.value = data.data[0];
            }
        } else {
            appendOutput(`Error loading PCAPs: ${data.error}\n`, 'error');
        }
    } catch (error) {
        appendOutput(`Failed to load PCAPs: ${error.message}\n`, 'error');
        pcapSelect.innerHTML = '<option value="">Error loading PCAP files</option>';
    }
}

async function startReplay() {
    const config = {
        interface: interfaceSelect.value,
        pcap: pcapSelect.value,
        pps: parseInt(ppsInput.value) || 0,
        loop: parseInt(loopInput.value) || 1
    };
    
    if (!config.interface || !config.pcap) {
        appendOutput('Error: Please select both interface and PCAP file\n', 'error');
        return;
    }
    
    try {
        appendOutput('═'.repeat(60) + '\n', 'info');
        appendOutput('▶ Starting packet replay...\n', 'info');
        appendOutput(`Interface: ${config.interface}\n`, 'info');
        appendOutput(`PCAP: ${config.pcap}\n`, 'info');
        appendOutput(`PPS: ${config.pps === 0 ? 'original timing' : config.pps}\n`, 'info');
        appendOutput(`Loop: ${config.loop}\n`, 'info');
        appendOutput('═'.repeat(60) + '\n\n', 'info');
        
        const response = await fetch(`${API_BASE}/replay`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(config)
        });
        
        const data = await response.json();
        
        if (data.success) {
            appendOutput(`✓ ${data.message}\n`, 'success');
            appendOutput(`Command: ${data.command}\n\n`, 'info');
            setRunningState(true);
        } else {
            appendOutput(`✗ Error: ${data.error}\n`, 'error');
        }
    } catch (error) {
        appendOutput(`✗ Failed to start replay: ${error.message}\n`, 'error');
    }
}

async function stopReplay() {
    try {
        const response = await fetch(`${API_BASE}/stop`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success) {
            appendOutput(`\n⏹ ${data.message}\n`, 'warning');
            setRunningState(false);
        } else {
            appendOutput(`✗ Error: ${data.error}\n`, 'error');
        }
    } catch (error) {
        appendOutput(`✗ Failed to stop replay: ${error.message}\n`, 'error');
    }
}

async function checkStatus() {
    try {
        const response = await fetch(`${API_BASE}/status`);
        const data = await response.json();
        
        if (data.success) {
            const running = data.data.running;
            if (isRunning !== running) {
                setRunningState(running);
            }
        }
    } catch (error) {
        // Silent fail for status checks
        console.error('Status check failed:', error);
    }
}

function setRunningState(running) {
    isRunning = running;
    
    if (running) {
        fireBtn.disabled = true;
        stopBtn.disabled = false;
        statusText.textContent = 'Running...';
        statusIndicator.className = 'status-indicator running';
    } else {
        fireBtn.disabled = false;
        stopBtn.disabled = true;
        statusText.textContent = 'Ready';
        statusIndicator.className = 'status-indicator idle';
    }
}

function clearOutput() {
    outputBox.textContent = '';
}

function appendOutput(text, type = 'normal') {
    const span = document.createElement('span');
    span.textContent = text;
    
    // Color coding based on type
    switch(type) {
        case 'error':
            span.style.color = '#ef4444';
            break;
        case 'success':
            span.style.color = '#10b981';
            break;
        case 'warning':
            span.style.color = '#f59e0b';
            break;
        case 'info':
            span.style.color = '#60a5fa';
            break;
        default:
            span.style.color = '#d4d4d4';
    }
    
    outputBox.appendChild(span);
    outputBox.scrollTop = outputBox.scrollHeight;
}

// Log initial message
appendOutput('PacketTester Web Interface Loaded\n', 'success');
appendOutput('Select a PCAP file and interface to begin\n\n', 'info');

