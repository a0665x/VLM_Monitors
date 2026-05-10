// ==================== Global State ====================
let socket = null;
let hls = null;

// ==================== Utilities ====================
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

const state = {
    connected: false,
    autoAnalysis: false,
    soundDetection: false,
    currentRisk: false,
    analysisRunning: false,
    selectedSourceId: 'agx-local',
    selectedSourceLabel: 'AGX Local Camera',
    clientId: '',
    sources: [],
    situationRoomClientId: '',
    gridSignature: '',
    heartbeatTimer: null,
    sourcesPollTimer: null,
    mode: 'camera',
    cameraPublisherActive: false,
    roleChosen: false,
    inferenceOverlayEnabled: false,
    inferenceOverlayText: '',
    overlaySourceId: 'agx-local',
    publicUrls: {
        ui: '',
        webrtc: ''
    }
};

// ==================== Initialize ====================
document.addEventListener('DOMContentLoaded', () => {
    state.clientId = getClientId();
    initializeWebSocket();
    initializeEventListeners();
    loadInitialData().then(() => {
        initializeVideoPlayer();
        updateStreamUrls();
        updateCameraSecurityHint();
        bootstrapPreferredRole();
    });
    initializeAccordion();
    initializeModeSwitcher();
    startSourcesPolling();
});

// ==================== WebSocket ====================
function initializeWebSocket() {
    socket = io({
        reconnection: true,
        reconnectionDelay: 1000,
        reconnectionAttempts: 10
    });

    socket.on('connect', () => {
        console.log('WebSocket connected');
        state.connected = true;
        updateConnectionStatus(true);
        socket.emit('request_status');
    });

    socket.on('disconnect', () => {
        console.log('WebSocket disconnected');
        state.connected = false;
        updateConnectionStatus(false);
    });

    socket.on('status_update', (data) => {
        updateRiskStatus(data);
    });

    socket.on('sources_update', (data) => {
        updateSources(data);
    });

    socket.on('metrics_update', (data) => {
        updateSystemMetrics(data);
    });

    socket.on('inference_stream', (data) => {
        state.inferenceOverlayEnabled = !!data.enabled;
        state.overlaySourceId = data.source_id || state.selectedSourceId;
        state.inferenceOverlayText = data.text || '';
        updateSourceTileStates();
    });
}

function updateConnectionStatus(connected) {
    const statusDot = document.getElementById('ws-status');
    const statusText = document.getElementById('ws-status-text');

    if (connected) {
        statusDot.classList.add('connected');
        statusText.textContent = 'Connected';
    } else {
        statusDot.classList.remove('connected');
        statusText.textContent = 'Disconnected';
    }
}

// ==================== Video Player ====================
function initializeVideoPlayer() {
    renderSourceGrid();
}

function useWebRtcPlayer() {
    renderSourceGrid();
}

function useHlsPlayer() {
    renderSourceGrid();
}

function updateStreamUrls() {
    const selected = state.sources.find((source) => source.id === state.selectedSourceId);
    const streamUrl = selected ? getSourceWebRtcUrl(selected) : `${getWebRtcBaseUrl()}/camera`;
    setText('stream-url', streamUrl ? `WebRTC live view: ${streamUrl}` : 'Waiting for source');
    setText('selected-source-label', selected ? `${selected.label} (${selected.id})` : 'Waiting for source');
}

function getWebRtcBaseUrl() {
    const host = window.location.hostname || 'localhost';
    if (window.location.protocol === 'https:' && state.publicUrls.webrtc) {
        return state.publicUrls.webrtc.replace(/\/$/, '');
    }
    return `http://${host}:8889`;
}

function getSourceWebRtcUrl(source) {
    const path = source?.path || (source?.id === 'agx-local' ? 'camera' : source?.id || 'camera');
    return `${getWebRtcBaseUrl()}/${path}`;
}

function shouldUseProxyHlsPlayback() {
    return window.location.protocol === 'https:' && state.mode === 'situation';
}

function getSourcePlaybackUrl(source) {
    const path = source?.path || (source?.id === 'agx-local' ? 'camera' : source?.id || 'camera');
    return `/proxy/hls/${path}/index.m3u8`;
}

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) {
        el.textContent = value;
    }
}

function getClientId() {
    const key = 'llm-monitor-client-id';
    let value = window.localStorage.getItem(key);
    if (!value) {
        value = `client-${Math.random().toString(36).slice(2, 10)}`;
        window.localStorage.setItem(key, value);
    }
    return value;
}

function getStoredRole() {
    try {
        return window.localStorage.getItem('llm-monitor-role') || '';
    } catch (error) {
        return '';
    }
}

function storeRole(role) {
    try {
        window.localStorage.setItem('llm-monitor-role', role);
    } catch (error) {
        console.warn('Failed to persist role selection', error);
    }
}

function normalizeSourceId(value) {
    return (value || 'browser-src')
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9_-]+/g, '-')
        .replace(/^-+|-+$/g, '') || 'browser-src';
}

function updateCameraPublisher(startRequested = false) {
    const input = document.getElementById('camera-source-id');
    const labelInput = document.getElementById('camera-source-label');
    if (!input) {
        return;
    }
    const needsHttps = window.location.protocol !== 'https:' && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
    if (needsHttps) {
        updateCameraSecurityHint();
        return;
    }

    const sourceId = normalizeSourceId(input.value);
    input.value = sourceId;
    if (labelInput && !labelInput.value.trim()) {
        labelInput.value = sourceId;
    }

    if (!startRequested && !state.cameraPublisherActive) {
        setText('camera-publish-status', 'Ready. Fill source info, then press Start Camera Sharing.');
        return;
    }

    const nextSrc = `${getWebRtcBaseUrl()}/${sourceId}/publish`;
    state.cameraPublisherActive = true;
    registerCameraSource(sourceId, labelInput ? labelInput.value.trim() : sourceId);
    startSourceHeartbeat();
    setText('camera-publish-status', `Source ${sourceId} registered. Camera publisher will open now.`);
    window.open(nextSrc, '_blank', 'noopener');
}

function initializeModeSwitcher() {
    document.querySelectorAll('.mode-button').forEach(button => {
        button.addEventListener('click', () => setMode(button.dataset.mode));
    });
    document.querySelectorAll('.segment-option').forEach(button => {
        button.addEventListener('click', () => setMode(button.dataset.mode));
    });
}

function showRoleGate() {
    const gate = document.getElementById('role-gate');
    if (gate) {
        gate.classList.remove('hidden');
    }
}

function hideRoleGate() {
    const gate = document.getElementById('role-gate');
    if (gate) {
        gate.classList.add('hidden');
    }
}

function bootstrapPreferredRole() {
    const preferredRole = getStoredRole();
    if (preferredRole === 'situation' || preferredRole === 'camera') {
        setText('role-gate-status', `Restoring previous role: ${preferredRole}.`);
        setMode(preferredRole);
        return;
    }
    showRoleGate();
}

async function setMode(mode) {
    const sourceId = normalizeSourceId(document.getElementById('camera-source-id')?.value || 'browser-src');
    const sourceLabel = (document.getElementById('camera-source-label')?.value || sourceId).trim();
    try {
        const response = await fetch('/api/mode', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                mode,
                client_id: state.clientId,
                source_id: sourceId,
                label: sourceLabel,
                register_source: false
            })
        });
        const data = await response.json();
        if (!data.success) {
            if (data.forced_mode) {
                mode = data.forced_mode;
                showToast('Situation Room is already active; switched to Camera SRC', 'error');
            } else {
                showToast(data.error || 'Failed to switch mode', 'error');
                return;
            }
        }
        state.situationRoomClientId = data.situation_room_client_id || '';
        state.selectedSourceId = data.selected_source_id || state.selectedSourceId;
    } catch (error) {
        console.error('Mode switch error:', error);
        showToast('Failed to switch mode', 'error');
        return;
    }

    state.mode = mode;
    state.roleChosen = true;
    storeRole(mode);
    document.querySelectorAll('.segment-option').forEach(button => {
        button.classList.toggle('active', button.dataset.mode === mode);
        button.setAttribute('aria-checked', button.dataset.mode === mode ? 'true' : 'false');
    });

    const situation = document.getElementById('situation-room-view');
    const camera = document.getElementById('camera-src-view');
    const riskPanel = document.querySelector('.control-panel');

    situation.classList.toggle('hidden', mode !== 'situation');
    camera.classList.toggle('hidden', mode !== 'camera');
    riskPanel.classList.toggle('hidden', mode !== 'situation');
    hideRoleGate();

    if (mode === 'camera') {
        updateCameraSecurityHint();
        updateCameraPublisher(false);
    } else {
        stopSourceHeartbeat();
        state.cameraPublisherActive = false;
        setText('camera-publish-status', 'Ready. Fill source info, then press Start Camera Sharing.');
    }
    await loadSources();
    renderSourceGrid();
}

function startSourcesPolling() {
    if (state.sourcesPollTimer) {
        window.clearInterval(state.sourcesPollTimer);
    }
    state.sourcesPollTimer = window.setInterval(() => {
        if (state.mode === 'situation') {
            loadSources();
        }
    }, 3000);
}

async function registerCameraSource(sourceId, label) {
    try {
        await fetch('/api/sources/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ source_id: sourceId, label })
        });
    } catch (error) {
        console.error('Register source error:', error);
    }
}

function stopSourceHeartbeat() {
    if (state.heartbeatTimer) {
        window.clearInterval(state.heartbeatTimer);
        state.heartbeatTimer = null;
    }
}

function startSourceHeartbeat() {
    stopSourceHeartbeat();
    const tick = async () => {
        if (!state.cameraPublisherActive) {
            return;
        }
        const sourceId = normalizeSourceId(document.getElementById('camera-source-id')?.value || 'browser-src');
        const label = (document.getElementById('camera-source-label')?.value || sourceId).trim();
        await registerCameraSource(sourceId, label);
        try {
            await fetch('/api/sources/heartbeat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ source_id: sourceId })
            });
        } catch (error) {
            console.error('Source heartbeat error:', error);
        }
    };
    tick();
    state.heartbeatTimer = window.setInterval(tick, 5000);
}

function updateSources(data) {
    const nextSources = Array.isArray(data.sources) ? data.sources : [];
    const previousCount = state.sources.length;
    state.sources = nextSources;
    state.selectedSourceId = data.selected_source_id || state.selectedSourceId;
    state.situationRoomClientId = data.situation_room_client_id || '';
    if (previousCount !== nextSources.length) {
        state.gridSignature = '';
    }
    renderSourceGrid();
    syncModeAvailability();
}

function syncModeAvailability() {
    const roomStatus = document.getElementById('room-lock-status');
    const situationButton = document.getElementById('situation-room-mode');
    const cameraStatus = document.getElementById('camera-src-status');
    const cameraStatusCopy = document.getElementById('camera-src-status-copy');
    if (roomStatus) {
        roomStatus.textContent = 'Shared Situation Room control';
    }
    if (situationButton) {
        situationButton.disabled = false;
        situationButton.title = 'All Situation Room clients control the same backend state';
    }
    if (cameraStatus) {
        cameraStatus.textContent = 'This device can publish as Camera SRC';
    }
    if (cameraStatusCopy) {
        cameraStatusCopy.textContent = 'Start Camera Sharing opens the publisher directly. Phones must use an HTTPS UI URL before sharing camera.';
    }
}

function gridClassForCount(count) {
    if (count <= 1) return 'grid-1';
    if (count === 2) return 'grid-2';
    if (count <= 4) return 'grid-2';
    return 'grid-3';
}

function renderSourceGrid() {
    const grid = document.getElementById('source-grid');
    if (!grid) {
        return;
    }
    const sources = state.sources.length ? state.sources : [{
        id: 'agx-local',
        label: 'AGX Local Camera',
        status: 'online',
        webrtc_url: `${getWebRtcBaseUrl()}/camera`,
        is_local: true
    }];
    const signature = JSON.stringify({
        sources: sources.map((source) => [source.id, source.status, source.label, source.webrtc_url]),
        mode: state.mode
    });
    if (signature === state.gridSignature) {
        updateStreamUrls();
        updateSourceTileStates();
        return;
    }
    state.gridSignature = signature;
    grid.className = `source-grid situation-grid ${gridClassForCount(sources.length)}`;
    grid.innerHTML = sources.map((source) => {
        const selected = source.id === state.selectedSourceId;
        const isRisk = selected && state.currentRisk;
        const statusClass = source.status === 'online' ? 'online' : 'offline';
        const streamMarkup = shouldUseProxyHlsPlayback()
            ? `<video class="source-video" title="${escapeHtml(source.label || source.id)} stream" src="${getSourcePlaybackUrl(source)}" autoplay muted playsinline controls></video>`
            : `<iframe class="webrtc-frame" title="${escapeHtml(source.label || source.id)} stream" src="${getSourceWebRtcUrl(source)}" allow="autoplay; fullscreen; microphone; camera"></iframe>`;
        return `
            <article class="source-tile ${selected ? 'monitored' : ''} ${source.status !== 'online' ? 'offline' : ''} ${isRisk ? 'risk' : ''}" data-source-id="${source.id}">
                <div class="source-tile-header">
                    <div>
                        <div class="source-tile-title">${escapeHtml(source.label || source.id)}</div>
                        <div class="source-status ${statusClass}">${source.status === 'online' ? 'ONLINE' : 'OFFLINE'}</div>
                    </div>
                    <div class="source-header-actions">
                        <button class="source-monitor-button ${selected ? 'active' : ''}" data-select-source="${source.id}" ${source.status !== 'online' ? 'disabled' : ''}>${selected ? 'Monitoring' : 'Monitor'}</button>
                        <span class="source-tile-badge" style="${selected ? '' : 'display:none;'}">MONITORED</span>
                    </div>
                </div>
                <div class="source-tile-stream">
                    ${streamMarkup}
                    <div class="source-stream-overlay ${selected && state.inferenceOverlayEnabled && state.overlaySourceId === source.id && state.inferenceOverlayText ? 'active' : ''}" data-overlay-source="${source.id}">
                        <div class="source-stream-overlay-text">${escapeHtml(selected && state.overlaySourceId === source.id ? state.inferenceOverlayText : '')}</div>
                    </div>
                </div>
                <div class="source-tile-meta">
                    <span>${escapeHtml(source.id)}</span>
                    <div class="source-tile-actions">
                        ${source.is_local ? '' : '<button class="source-disconnect-button" data-disconnect-source="' + escapeHtml(source.id) + '">Disconnect</button>'}
                    </div>
                </div>
            </article>
        `;
    }).join('');

    grid.querySelectorAll('.source-tile').forEach((tile) => {
        tile.addEventListener('click', async (event) => {
            if (event.target.closest('button')) {
                return;
            }
            const sourceId = tile.getAttribute('data-source-id');
            await selectSource(sourceId);
        });
    });

    grid.querySelectorAll('[data-select-source]').forEach((button) => {
        button.addEventListener('click', async () => {
            const sourceId = button.getAttribute('data-select-source');
            await selectSource(sourceId);
        });
    });

    grid.querySelectorAll('[data-disconnect-source]').forEach((button) => {
        button.addEventListener('click', async () => {
            const sourceId = button.getAttribute('data-disconnect-source');
            try {
                const response = await fetch('/api/sources/disconnect', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ source_id: sourceId })
                });
                const data = await response.json();
                if (!data.success) {
                    showToast(data.error || 'Failed to disconnect source', 'error');
                    return;
                }
                showToast(`Disconnected ${sourceId}`);
                await loadSources();
                await loadStatus();
            } catch (error) {
                console.error('Disconnect source error:', error);
                showToast('Failed to disconnect source', 'error');
            }
        });
    });
    updateStreamUrls();
    updateSourceTileStates();
}

async function selectSource(sourceId) {
    try {
        const response = await fetch('/api/sources/select', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ source_id: sourceId })
        });
        const data = await response.json();
        if (!data.success) {
            showToast(data.error || 'Failed to switch source', 'error');
            return;
        }
        if (data.status) {
            updateRiskStatus(data.status);
        }
        state.selectedSourceId = data.selected_source_id || sourceId;
        updateSourceTileStates();
    } catch (error) {
        console.error('Select source error:', error);
    }
}

function updateSourceTileStates() {
    const grid = document.getElementById('source-grid');
    if (!grid) {
        return;
    }
    grid.querySelectorAll('.source-tile').forEach((tile) => {
        const sourceId = tile.getAttribute('data-source-id');
        const selected = sourceId === state.selectedSourceId;
        const isRisk = selected && state.currentRisk;
        tile.classList.toggle('monitored', selected);
        tile.classList.toggle('risk', isRisk);

        const badge = tile.querySelector('.source-tile-badge');
        if (badge) {
            badge.style.display = selected ? 'inline-flex' : 'none';
        }

        const monitorButton = tile.querySelector('.source-monitor-button');
        if (monitorButton) {
            monitorButton.classList.toggle('active', selected);
            monitorButton.textContent = selected ? 'Monitoring' : 'Monitor';
        }

        const overlay = tile.querySelector(`[data-overlay-source="${sourceId}"]`);
        if (overlay) {
            const shouldShow = selected
                && state.inferenceOverlayEnabled
                && state.overlaySourceId === sourceId
                && !!state.inferenceOverlayText;
            overlay.classList.toggle('active', shouldShow);
            const textEl = overlay.querySelector('.source-stream-overlay-text');
            if (textEl) {
                textEl.textContent = shouldShow ? state.inferenceOverlayText : '';
            }
        }
    });
    updateStreamUrls();
}

function escapeHtml(value) {
    return String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
}

// ==================== Event Listeners ====================
function initializeEventListeners() {
    const reloadCameraSrcButton = document.getElementById('reload-camera-src-btn');
    if (reloadCameraSrcButton) {
        reloadCameraSrcButton.addEventListener('click', () => updateCameraPublisher(true));
    }

    const enterSituationRoomButton = document.getElementById('enter-situation-room-btn');
    if (enterSituationRoomButton) {
        enterSituationRoomButton.addEventListener('click', () => {
            setText('role-gate-status', 'Requesting Situation Room...');
            setMode('situation');
        });
    }

    const enterCameraSrcButton = document.getElementById('enter-camera-src-btn');
    if (enterCameraSrcButton) {
        enterCameraSrcButton.addEventListener('click', () => {
            setText('role-gate-status', 'Joining as Camera SRC...');
            setMode('camera');
        });
    }

    const cameraSourceInput = document.getElementById('camera-source-id');
    if (cameraSourceInput) {
        cameraSourceInput.addEventListener('change', () => updateCameraPublisher(state.cameraPublisherActive));
    }

    const cameraSourceLabelInput = document.getElementById('camera-source-label');
    if (cameraSourceLabelInput) {
        cameraSourceLabelInput.addEventListener('change', () => updateCameraPublisher(state.cameraPublisherActive));
    }

    // Analyze Once
    document.getElementById('analyze-once-btn').addEventListener('click', async () => {
        try {
            const response = await fetch('/api/analysis/trigger', { method: 'POST' });
            const data = await response.json();
            if (data.success) {
                showToast('Analysis triggered!');
            } else if (data.busy) {
                showToast(data.message || 'Analysis is already running', 'error');
            } else {
                showToast(data.error || 'Failed to trigger analysis', 'error');
            }
        } catch (error) {
            console.error('Trigger error:', error);
            showToast('Failed to trigger analysis', 'error');
        }
    });

    // Auto Analysis Toggle
    document.getElementById('auto-analysis-toggle').addEventListener('change', async (e) => {
        const enabled = e.target.checked;
        try {
            const response = await fetch('/api/analysis/auto', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled })
            });
            const data = await response.json();
            if (data.success) {
                state.autoAnalysis = enabled;
                document.getElementById('notification-controls').style.display = enabled ? 'block' : 'none';
                showToast(enabled ? 'Auto analysis enabled' : 'Auto analysis disabled');
                loadStatus();
            }
        } catch (error) {
            console.error('Auto analysis toggle error:', error);
        }
    });

    // Sound Detection Toggle
    document.getElementById('sound-detection-toggle').addEventListener('change', async (e) => {
        const enabled = e.target.checked;
        try {
            const response = await fetch('/api/sound/toggle', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    enabled,
                    threshold_db: parseFloat(document.getElementById('sound-threshold-slider').value)
                })
            });
            const data = await response.json();
            if (data.success) {
                state.soundDetection = enabled;
                document.getElementById('sound-info').style.display = enabled ? 'flex' : 'none';
                if (data.status) {
                    updateRiskStatus(data.status);
                }
                showToast(enabled ? 'Sound detection enabled' : 'Sound detection disabled');
            }
        } catch (error) {
            console.error('Sound toggle error:', error);
        }
    });

    const debouncedSyncThreshold = debounce(async (threshold) => {
        try {
            const response = await fetch('/api/sound/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ threshold_db: threshold })
            });
            const data = await response.json();
            if (data.status) {
                updateRiskStatus(data.status);
            }
        } catch (error) {
            console.error('Sound config error:', error);
        }
    }, 150);

    document.getElementById('sound-threshold-slider').addEventListener('input', (e) => {
        const threshold = parseFloat(e.target.value);
        setText('sound-threshold-value', `${threshold.toFixed(0)} dB`);
        updateSoundThresholdMarker(threshold);
        debouncedSyncThreshold(threshold);
    });

    // SMS Toggle
    document.getElementById('enable-sms-toggle').addEventListener('change', async (e) => {
        await updateNotificationSettings({ enable_sms: e.target.checked });
    });

    // Webhook Toggle
    document.getElementById('enable-webhook-toggle').addEventListener('change', async (e) => {
        await updateNotificationSettings({ enable_webhook: e.target.checked });
    });

    const webhookUrlInput = document.getElementById('webhook-url');
    if (webhookUrlInput) {
        webhookUrlInput.addEventListener('change', async (e) => {
            await updateNotificationSettings({ webhook_url: e.target.value.trim() });
        });
    }

    // Analysis Settings Sliders
    document.getElementById('interval-slider').addEventListener('input', (e) => {
        document.getElementById('interval-value').textContent = Number(e.target.value) === 0 ? '0s (max)' : `${e.target.value}s`;
    });

    document.getElementById('interval-slider').addEventListener('change', async (e) => {
        await updateAnalysisConfig({ interval: e.target.value });
    });

    document.getElementById('threshold-slider').addEventListener('input', (e) => {
        document.getElementById('threshold-value').textContent = e.target.value;
    });

    document.getElementById('threshold-slider').addEventListener('change', async (e) => {
        await updateAnalysisConfig({ threshold: e.target.value });
    });

    const overlayToggle = document.getElementById('show-inference-overlay-toggle');
    if (overlayToggle) {
        overlayToggle.addEventListener('change', async (e) => {
            await updateAnalysisConfig({ show_inference_overlay: e.target.checked });
        });
    }

    // Model Selection
    document.getElementById('model-select').addEventListener('change', async (e) => {
        await updateAnalysisConfig({ model: e.target.value });
        showToast('Model updated. Restarting analysis with new model...');
    });

    // Save Twilio Config
    document.getElementById('save-twilio-btn').addEventListener('click', async () => {
        const config = {
            sid: document.getElementById('twilio-sid').value,
            token: document.getElementById('twilio-token').value,
            from_number: document.getElementById('from-number').value,
            to_number: document.getElementById('to-number').value,
            custom_msg: document.getElementById('custom-msg').value,
            cooldown: parseInt(document.getElementById('cooldown-input').value)
        };

        try {
            const response = await fetch('/api/config/twilio', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            });
            const data = await response.json();
            if (data.success) {
                showToast('Twilio configuration saved!');
                if (data.status) {
                    updateRiskStatus(data.status);
                }
            } else {
                showToast('Failed to save: ' + data.error, 'error');
            }
        } catch (error) {
            console.error('Save config error:', error);
            showToast('Failed to save configuration', 'error');
        }
    });

    // Apply Device Settings
    document.getElementById('apply-device-btn').addEventListener('click', async () => {
        const videoDevice = document.getElementById('video-device-select').value;
        const audioDevice = document.getElementById('audio-device-select').value;
        const enableAudio = document.getElementById('enable-audio-toggle').checked;

        try {
            const response = await fetch('/api/devices/switch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    video_device: videoDevice,
                    audio_device: audioDevice,
                    enable_audio: enableAudio
                })
            });
            const data = await response.json();
            if (data.success) {
                showToast(data.message);
                // Reload video player after device switch
                setTimeout(() => {
                    if (hls) {
                        hls.destroy();
                    }
                    initializeVideoPlayer();
                }, 1000);
            } else {
                showToast('Failed to switch: ' + data.error, 'error');
            }
        } catch (error) {
            console.error('Device switch error:', error);
            showToast('Failed to switch device', 'error');
        }
    });

    // Apply Prompt
    document.getElementById('apply-prompt-btn').addEventListener('click', async () => {
        const text = document.getElementById('prompt-textarea').value;
        applyPromptText(text);
    });

    // Prompt History Selection
    document.getElementById('prompt-history').addEventListener('change', async (e) => {
        if (e.target.value) {
            document.getElementById('prompt-textarea').value = e.target.value;
            await applyPromptText(e.target.value);
        }
    });
}

async function applyPromptText(text) {
    try {
        const response = await fetch('/api/prompt/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text })
        });
        const data = await response.json();
        if (data.success) {
            showToast('Risk criteria updated!');
            if (data.status) {
                updateRiskStatus(data.status);
            }
            loadPromptHistory();
        } else {
            showToast('Failed to update: ' + data.error, 'error');
        }
    } catch (error) {
        console.error('Prompt update error:', error);
        showToast('Failed to update prompt', 'error');
    }
}

// ==================== Data Loading ====================
async function loadInitialData() {
    await Promise.all([
        loadPublicUrls(),
        loadStatus(),
        loadSources(),
        loadMetrics(),
        loadVisionModels(),
        loadVideoDevices(),
        loadAudioDevices(),
        loadCurrentPrompt(),
        loadPromptHistory()
    ]);
}

async function loadPublicUrls() {
    try {
        const response = await fetch('/api/public-urls');
        const data = await response.json();
        const previousWebRtc = state.publicUrls.webrtc;
        state.publicUrls = {
            ui: data.ui || '',
            webrtc: data.webrtc || ''
        };
        if (window.location.protocol === 'https:' && state.publicUrls.webrtc) {
            console.log('Using secure WebRTC base URL:', state.publicUrls.webrtc);
        }
        if (previousWebRtc !== state.publicUrls.webrtc) {
            state.gridSignature = '';
            renderSourceGrid();
        }
    } catch (error) {
        console.error('Load public URLs error:', error);
    }
}

async function loadStatus() {
    try {
        const response = await fetch('/api/status');
        const data = await response.json();
        updateRiskStatus(data);
    } catch (error) {
        console.error('Load status error:', error);
    }
}

async function loadSources() {
    try {
        const response = await fetch('/api/sources');
        const data = await response.json();
        updateSources(data);
    } catch (error) {
        console.error('Load sources error:', error);
    }
}

async function loadMetrics() {
    try {
        const response = await fetch('/api/metrics');
        const data = await response.json();
        updateSystemMetrics(data);
    } catch (error) {
        console.error('Load metrics error:', error);
    }
}

async function loadVisionModels() {
    try {
        const response = await fetch('/api/models/vision');
        const data = await response.json();
        const select = document.getElementById('model-select');
        select.innerHTML = '';
        data.models.forEach(model => {
            const option = document.createElement('option');
            option.value = model;
            option.textContent = model;
            if (model === data.current) {
                option.selected = true;
            }
            select.appendChild(option);
        });
    } catch (error) {
        console.error('Load models error:', error);
    }
}

async function loadVideoDevices() {
    try {
        const response = await fetch('/api/devices/video');
        const data = await response.json();
        const select = document.getElementById('video-device-select');
        select.innerHTML = '';
        data.devices.forEach(device => {
            const option = document.createElement('option');
            option.value = device;
            option.textContent = device;
            if (device === data.current) {
                option.selected = true;
            }
            select.appendChild(option);
        });
    } catch (error) {
        console.error('Load video devices error:', error);
    }
}

async function loadAudioDevices() {
    try {
        const response = await fetch('/api/devices/audio');
        const data = await response.json();
        const select = document.getElementById('audio-device-select');
        select.innerHTML = '';
        data.devices.forEach(device => {
            const option = document.createElement('option');
            option.value = device;
            option.textContent = device;
            if (device === data.current) {
                option.selected = true;
            }
            select.appendChild(option);
        });
    } catch (error) {
        console.error('Load audio devices error:', error);
    }
}

async function loadCurrentPrompt() {
    try {
        const response = await fetch('/api/prompt/current');
        const data = await response.json();
        document.getElementById('prompt-textarea').value = data.text;
    } catch (error) {
        console.error('Load prompt error:', error);
    }
}

async function loadPromptHistory() {
    try {
        const response = await fetch('/api/prompt/history');
        const data = await response.json();
        const select = document.getElementById('prompt-history');
        select.innerHTML = '<option value="">Select from history...</option>';
        data.history.forEach(text => {
            const option = document.createElement('option');
            option.value = text;
            option.textContent = text.substring(0, 50) + (text.length > 50 ? '...' : '');
            select.appendChild(option);
        });
    } catch (error) {
        console.error('Load history error:', error);
    }
}

// ==================== Update Functions ====================
function updateRiskStatus(data) {
    const isRisk = data.risk;
    const score = data.score || 0;
    const isRunning = !!data.analysis_running;
    const explanation = data.last_inference_error || data.explanation || 'Waiting for analysis...';
    state.selectedSourceId = data.source_id || state.selectedSourceId;
    state.selectedSourceLabel = data.source_label || state.selectedSourceLabel;
    state.analysisRunning = !!data.analysis_running;
    state.inferenceOverlayEnabled = !!data.show_inference_overlay;
    state.overlaySourceId = data.source_id || state.overlaySourceId;
    if (!state.analysisRunning && data.streaming_inference_text !== undefined) {
        state.inferenceOverlayText = data.streaming_inference_text || '';
    }

    // Update status indicator
    const statusIndicator = document.getElementById('status-indicator');
    const statusText = document.getElementById('status-text');

    if (isRunning) {
        statusIndicator.classList.remove('risk');
        statusIndicator.classList.add('analyzing');
        statusText.textContent = 'ANALYZING';
    } else if (isRisk) {
        statusIndicator.classList.remove('analyzing');
        statusIndicator.classList.add('risk');
        statusText.textContent = 'RISK DETECTED';
    } else {
        statusIndicator.classList.remove('analyzing');
        statusIndicator.classList.remove('risk');
        statusText.textContent = 'SAFE';
    }

    // Update confidence meter
    const confidenceFill = document.getElementById('confidence-fill');
    const confidenceValue = document.getElementById('confidence-value');
    confidenceFill.style.width = (score * 100) + '%';
    confidenceValue.textContent = score.toFixed(2);

    // Update explanation
    document.getElementById('explanation-text').textContent = explanation;
    updateInferenceMeta(data);

    // Update sound info if enabled
    updateSoundMeter(data);

    state.currentRisk = isRisk;
    state.autoAnalysis = !!data.auto_analyze;
    syncAnalysisControls(data);
    updateSourceTileStates();
}

function dbToPercent(db) {
    const clamped = Math.max(-80, Math.min(0, Number.isFinite(db) ? db : -80));
    return ((clamped + 80) / 80) * 100;
}

function updateSoundThresholdMarker(threshold) {
    const marker = document.getElementById('sound-threshold-marker');
    if (marker) {
        marker.style.left = `${dbToPercent(threshold)}%`;
    }
}

function updateSoundMeter(data) {
    const soundInfo = document.getElementById('sound-info');
    const enabled = !!data.sound_detection_enabled;
    if (soundInfo) {
        soundInfo.style.display = enabled ? 'flex' : 'none';
    }
    const toggle = document.getElementById('sound-detection-toggle');
    if (toggle) {
        toggle.checked = enabled;
    }

    const db = typeof data.sound_db === 'number' ? data.sound_db : -120;
    const threshold = typeof data.sound_threshold_db === 'number' ? data.sound_threshold_db : -35;
    const slider = document.getElementById('sound-threshold-slider');
    if (slider && document.activeElement !== slider) {
        slider.value = threshold;
    }

    setText('sound-label', data.sound_risk ? 'Volume trigger' : (data.sound_label || 'Listening'));
    setText('sound-fps', `FPS: ${(data.sound_fps || 0).toFixed(1)}`);
    setText('sound-db', `${db.toFixed(1)} dB`);
    setText('sound-threshold-value', `${threshold.toFixed(0)} dB`);
    updateSoundThresholdMarker(threshold);

    const fill = document.getElementById('sound-level-fill');
    if (fill) {
        fill.style.width = `${dbToPercent(db)}%`;
    }
}

function updateInferenceMeta(data) {
    const currentModel = data.scoring_model || data.last_inference_model || '--';
    setText('inference-model', currentModel);
    if (data.analysis_running) {
        setText('inference-latency', 'Running...');
    } else if (data.last_inference_latency_ms) {
        setText('inference-latency', `${(data.last_inference_latency_ms / 1000).toFixed(1)}s`);
    } else {
        setText('inference-latency', '--');
    }

    if (data.last_inference_at) {
        const dt = new Date(data.last_inference_at);
        setText('inference-last-run', Number.isNaN(dt.getTime()) ? data.last_inference_at : dt.toLocaleTimeString());
    } else {
        setText('inference-last-run', '--');
    }
}

function syncAnalysisControls(data) {
    const autoToggle = document.getElementById('auto-analysis-toggle');
    const analyzeButton = document.getElementById('analyze-once-btn');
    const notificationControls = document.getElementById('notification-controls');
    const smsToggle = document.getElementById('enable-sms-toggle');
    const webhookToggle = document.getElementById('enable-webhook-toggle');
    const intervalSlider = document.getElementById('interval-slider');
    const thresholdSlider = document.getElementById('threshold-slider');
    const overlayToggle = document.getElementById('show-inference-overlay-toggle');
    const modelSelect = document.getElementById('model-select');
    const webhookUrl = document.getElementById('webhook-url');
    const toNumber = document.getElementById('to-number');
    const cooldownInput = document.getElementById('cooldown-input');
    const customMessage = document.getElementById('custom-msg');

    if (autoToggle) {
        autoToggle.checked = !!data.auto_analyze;
    }
    if (analyzeButton) {
        analyzeButton.disabled = !!data.analysis_running;
        analyzeButton.classList.toggle('disabled', !!data.analysis_running);
    }
    if (notificationControls) {
        notificationControls.style.display = data.auto_analyze ? 'block' : 'none';
    }
    if (smsToggle) {
        smsToggle.checked = !!data.enable_sms;
    }
    if (webhookToggle) {
        webhookToggle.checked = !!data.enable_webhook;
    }
    if (intervalSlider && document.activeElement !== intervalSlider && typeof data.analysis_interval === 'number') {
        intervalSlider.value = String(data.analysis_interval);
        setText('interval-value', Number(data.analysis_interval) === 0 ? '0s (max)' : `${data.analysis_interval}s`);
    }
    if (thresholdSlider && document.activeElement !== thresholdSlider && typeof data.risk_threshold === 'number') {
        thresholdSlider.value = String(data.risk_threshold);
        setText('threshold-value', String(data.risk_threshold));
    }
    if (modelSelect && document.activeElement !== modelSelect && data.scoring_model) {
        modelSelect.value = data.scoring_model;
    }
    if (webhookUrl && document.activeElement !== webhookUrl) {
        webhookUrl.value = data.webhook_url || '';
    }
    if (toNumber && document.activeElement !== toNumber) {
        toNumber.value = data.alert_receiver || '';
    }
    if (cooldownInput && document.activeElement !== cooldownInput && typeof data.alert_cooldown === 'number') {
        cooldownInput.value = String(data.alert_cooldown);
    }
    if (customMessage && document.activeElement !== customMessage) {
        customMessage.value = data.custom_msg || '';
    }
    if (overlayToggle) {
        overlayToggle.checked = !!data.show_inference_overlay;
    }
}

function updateCameraSecurityHint() {
    const status = document.getElementById('camera-publish-status');
    const button = document.getElementById('reload-camera-src-btn');
    const needsHttps = window.location.protocol !== 'https:' && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
    if (needsHttps) {
        if (status) {
            status.textContent = 'Phone camera sharing requires HTTPS. Open the Public UI HTTPS link from run.sh before starting Camera SRC.';
        }
        if (button) {
            button.disabled = true;
        }
    } else if (button) {
        button.disabled = false;
    }
}

function updateSystemMetrics(data) {
    document.getElementById('cpu-usage').textContent = (data.cpu_percent || 0) + '%';

    if (data.ram) {
        document.getElementById('ram-usage').textContent = (data.ram.percent || 0) + '%';
    }

    if (data.gpu) {
        document.getElementById('gpu-usage').textContent = (data.gpu.utilization_percent || 0) + '%';
    } else {
        document.getElementById('gpu-usage').textContent = 'N/A';
    }
}

async function updateAnalysisConfig(config) {
    try {
        const response = await fetch('/api/analysis/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });
        const data = await response.json();
        if (!data.success) {
            showToast('Failed to update config', 'error');
        } else if (data.status) {
            updateRiskStatus(data.status);
        }
    } catch (error) {
        console.error('Update config error:', error);
    }
}

async function updateNotificationSettings(settings) {
    try {
        const response = await fetch('/api/config/notifications', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
        const data = await response.json();
        if (!data.success) {
            showToast('Failed to update notifications', 'error');
        } else if (data.status) {
            updateRiskStatus(data.status);
        }
    } catch (error) {
        console.error('Update notifications error:', error);
    }
}

// ==================== Accordion ====================
function initializeAccordion() {
    const headers = document.querySelectorAll('.accordion-header');

    headers.forEach(header => {
        header.addEventListener('click', () => {
            const target = header.getAttribute('data-target');
            const content = document.getElementById(target);
            const isActive = header.classList.contains('active');

            // Close all accordions
            document.querySelectorAll('.accordion-header').forEach(h => h.classList.remove('active'));
            document.querySelectorAll('.accordion-content').forEach(c => c.classList.remove('active'));

            // Open clicked accordion if it wasn't active
            if (!isActive) {
                header.classList.add('active');
                content.classList.add('active');
            }
        });
    });
}

// ==================== Toast Notification ====================
function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.classList.add('show');

    setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}
