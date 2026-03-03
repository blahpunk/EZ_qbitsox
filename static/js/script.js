const state = {
    initialSettingsLoaded: false,
    theme: 'light',
};

function el(id) {
    return document.getElementById(id);
}

function escapeHtml(value) {
    return String(value)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}

function showAction(message, isError = false) {
    const node = el('action-message');
    node.textContent = message;
    node.className = isError ? 'error' : 'muted';
}

function showQbTestResult(message, isError = false) {
    const node = el('qb-test-result');
    node.textContent = message;
    node.className = isError ? 'error' : 'muted';
}

function setTheme(theme) {
    const safeTheme = theme === 'dark' ? 'dark' : 'light';
    state.theme = safeTheme;
    document.documentElement.setAttribute('data-theme', safeTheme);
    localStorage.setItem('ez_qbitsox_theme', safeTheme);
}

function initTheme() {
    const saved = localStorage.getItem('ez_qbitsox_theme');
    if (saved === 'dark' || saved === 'light') {
        setTheme(saved);
        return;
    }
    const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    setTheme(prefersDark ? 'dark' : 'light');
}

function settingsPayloadFromForm() {
    return {
        qbittorrent: {
            host: el('qb-host').value.trim(),
            port: Number(el('qb-port').value),
            username: el('qb-username').value.trim(),
            password: el('qb-password').value,
        },
        service: {
            scan_interval_minutes: Number(el('scan-interval').value),
            retest_after_minutes: Number(el('retest-age').value),
            max_workers: Number(el('max-workers').value),
            connect_timeout_seconds: Number(el('socket-timeout').value),
            source_timeout_seconds: Number(el('source-timeout').value),
        },
        auto_apply: {
            enabled: el('auto-enabled').checked,
            interval_minutes: Number(el('auto-interval').value),
        },
    };
}

function applySettingsToForm(settings) {
    const qb = settings.qbittorrent || {};
    const service = settings.service || {};
    const autoApply = settings.auto_apply || {};

    el('qb-host').value = qb.host || '';
    el('qb-port').value = qb.port || 8080;
    el('qb-username').value = qb.username || '';
    el('qb-password').value = '';
    el('qb-password').placeholder = qb.password_set ? 'Stored securely (leave blank to keep)' : 'Set password';

    el('scan-interval').value = service.scan_interval_minutes || 30;
    el('retest-age').value = service.retest_after_minutes || 180;
    el('max-workers').value = service.max_workers || 50;
    el('socket-timeout').value = service.connect_timeout_seconds || 7;
    el('source-timeout').value = service.source_timeout_seconds || 20;

    el('auto-enabled').checked = Boolean(autoApply.enabled);
    el('auto-interval').value = autoApply.interval_minutes || 60;
}

function renderService(snapshot) {
    const service = snapshot.service || {};
    const scan = snapshot.scan || {};
    const counts = snapshot.counts || {};
    const autoApply = snapshot.auto_apply || {};

    el('service-state').textContent = service.status || '-';
    el('service-stage').textContent = service.stage || '-';

    const progress = service.progress || { tested: 0, total: 0 };
    el('service-progress').textContent = `${progress.tested || 0}/${progress.total || 0}`;
    el('scan-paused').textContent = scan.paused ? 'yes' : 'no';
    el('scan-current-proxy').textContent = scan.current_proxy || '-';

    el('count-known').textContent = counts.known_proxies ?? 0;
    el('count-passed').textContent = counts.passed_proxies ?? 0;
    el('last-started').textContent = service.last_run_started || '-';
    el('last-finished').textContent = service.last_run_finished || '-';
    el('next-run').textContent = service.next_run_at || '-';
    el('service-error').textContent = service.last_error || '-';

    el('last-auto').textContent = autoApply.last_applied_at || '-';
    el('last-applied-proxy').textContent = autoApply.last_applied_proxy || '-';

    const qbStatus = snapshot.qbittorrent_status === 'ok' ? '' : ' (connection issue)';
    el('qb-current').textContent = `qBittorrent current proxy: ${snapshot.qbittorrent_current_proxy || '-'}${qbStatus}`;

    el('service-summary').textContent =
        `Status: ${service.status || '-'} | Stage: ${service.stage || '-'} | Passed proxies: ${counts.passed_proxies ?? 0}`;
}

function renderProxies(proxies) {
    const body = el('proxies-body');
    if (!Array.isArray(proxies) || proxies.length === 0) {
        body.innerHTML = '<tr><td colspan="5">No fully passed proxies yet.</td></tr>';
        return;
    }

    body.innerHTML = proxies.map((entry) => {
        const latency = entry.latency_ms !== null && entry.latency_ms !== undefined ? entry.latency_ms : '-';
        const sourceCount = Array.isArray(entry.sources) ? entry.sources.length : 0;
        const proxyEscaped = escapeHtml(entry.proxy);
        return `<tr>
            <td>${proxyEscaped}</td>
            <td>${latency}</td>
            <td>${escapeHtml(entry.last_tested || '-')}</td>
            <td>${sourceCount}</td>
            <td><button class="apply-proxy" data-proxy="${proxyEscaped}">Apply</button></td>
        </tr>`;
    }).join('');
}

async function fetchState() {
    try {
        const response = await fetch('/api/state');
        const snapshot = await response.json();

        renderService(snapshot);
        renderProxies(snapshot.passed_proxies || []);

        if (!state.initialSettingsLoaded) {
            applySettingsToForm(snapshot.settings || {});
            state.initialSettingsLoaded = true;
        }
    } catch (error) {
        showAction(`Failed to fetch state: ${error}`, true);
    }
}

async function saveSettings(event) {
    event.preventDefault();

    try {
        const response = await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settingsPayloadFromForm()),
        });

        const data = await response.json();
        if (!response.ok || !data.ok) {
            showAction(data.message || 'Failed to save settings', true);
            return;
        }

        showAction(data.message || 'Settings saved');
        applySettingsToForm(data.settings || {});
        await fetchState();
    } catch (error) {
        showAction(`Failed to save settings: ${error}`, true);
    }
}

async function runNow() {
    try {
        const response = await fetch('/api/run-now', { method: 'POST' });
        const data = await response.json();
        if (!response.ok || !data.ok) {
            showAction(data.message || 'Failed to trigger update', true);
            return;
        }
        showAction(data.message || 'Update started');
        await fetchState();
    } catch (error) {
        showAction(`Failed to trigger update: ${error}`, true);
    }
}

async function postSimpleAction(endpoint, successFallback) {
    try {
        const response = await fetch(endpoint, { method: 'POST' });
        const data = await response.json();
        if (!response.ok || !data.ok) {
            showAction(data.message || 'Action failed', true);
            return;
        }
        showAction(data.message || successFallback);
        await fetchState();
    } catch (error) {
        showAction(`Action failed: ${error}`, true);
    }
}

async function testQbConnection() {
    try {
        const response = await fetch('/api/qb/test', { method: 'POST' });
        const data = await response.json();
        if (!response.ok || !data.ok) {
            showQbTestResult(data.message || 'qBittorrent connection test failed', true);
            return;
        }

        const version = data.version ? ` | version ${data.version}` : '';
        const currentProxy = data.current_proxy ? ` | proxy: ${data.current_proxy}` : '';
        showQbTestResult(`${data.message || 'qBittorrent connection OK'}${version}${currentProxy}`);
        await fetchState();
    } catch (error) {
        showQbTestResult(`qBittorrent connection test failed: ${error}`, true);
    }
}

async function applyBest() {
    try {
        const response = await fetch('/api/proxy/apply-best', { method: 'POST' });
        const data = await response.json();
        if (!response.ok || !data.ok) {
            showAction(data.message || 'Failed to apply best proxy', true);
            return;
        }
        showAction(data.message || 'Best proxy applied');
        await fetchState();
    } catch (error) {
        showAction(`Failed to apply best proxy: ${error}`, true);
    }
}

async function applyProxy(proxy) {
    try {
        const response = await fetch('/api/proxy/apply', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ proxy }),
        });
        const data = await response.json();
        if (!response.ok || !data.ok) {
            showAction(data.message || `Failed to apply ${proxy}`, true);
            return;
        }
        showAction(data.message || `Applied ${proxy}`);
        await fetchState();
    } catch (error) {
        showAction(`Failed to apply ${proxy}: ${error}`, true);
    }
}

function wireEvents() {
    el('settings-form').addEventListener('submit', saveSettings);
    el('test-qb').addEventListener('click', testQbConnection);
    el('run-now').addEventListener('click', runNow);
    el('stop-scan').addEventListener('click', () => postSimpleAction('/api/scan/stop', 'Stop requested'));
    el('resume-scan').addEventListener('click', () => postSimpleAction('/api/scan/resume', 'Scan resumed'));
    el('restart-scan').addEventListener('click', () => postSimpleAction('/api/scan/restart', 'Scan restarted from top'));
    el('clear-refetch').addEventListener('click', () => postSimpleAction('/api/scan/clear-refetch', 'Cache cleared and refetch started'));
    el('apply-best').addEventListener('click', applyBest);
    el('theme-toggle').addEventListener('click', () => {
        setTheme(state.theme === 'dark' ? 'light' : 'dark');
    });

    el('proxies-body').addEventListener('click', (event) => {
        const target = event.target;
        if (!target.classList.contains('apply-proxy')) {
            return;
        }
        const proxy = target.getAttribute('data-proxy');
        if (proxy) {
            applyProxy(proxy);
        }
    });
}

document.addEventListener('DOMContentLoaded', async () => {
    initTheme();
    wireEvents();
    await fetchState();
    setInterval(fetchState, 8000);
});
