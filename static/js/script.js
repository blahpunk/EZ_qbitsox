// static/js/script.js

let currentSort = { idx: null, asc: false }; // Preserve sorting across refreshes

function iconCell(passed) {
    if (passed === true) return '<span style="color: #28a745; font-size:1.2em;">&#10004;</span>';
    if (passed === false) return '<span style="color: #dc3545; font-size:1.2em;">&#10006;</span>';
    return '<span style="color: #6c757d; font-size:1.2em;">?</span>';
}

function setProxyQB(proxy, rowIndex) {
    fetch(`/set_proxy/${proxy}`)
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                updateCurrentProxies();
                alert(`qBittorrent proxy set to ${proxy}`);
                fetchQbConnectionStatus();
            } else {
                alert('Failed to set qBittorrent proxy.');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('An error occurred while setting the qBittorrent proxy.');
        });
}

function setProxyFF(proxy, rowIndex) {
    fetch(`/set_firefox_proxy/${proxy}`)
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                updateCurrentProxies();
                alert(`Firefox proxy set to ${proxy}`);
            } else {
                alert('Failed to set Firefox proxy.');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('An error occurred while setting the Firefox proxy.');
        });
}

function updateProxies() {
    const proxyTable = document.getElementById('proxy-table').getElementsByTagName('tbody')[0];
    proxyTable.innerHTML = '';
    const loadingRow = proxyTable.insertRow(0);
    loadingRow.innerHTML = `<td colspan="15">Updating proxies, please wait...</td>`;

    fetch('/update_proxies')
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                setTimeout(fetchProxies, 5000);
            } else {
                alert('Failed to update proxies.');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('An error occurred while updating the proxies.');
        });
}

function fetchProxies() {
    fetch('/proxies')
        .then(response => response.json())
        .then(data => {
            const proxies = data.proxies;
            const lastUpdate = data.last_update;
            const proxyTable = document.getElementById('proxy-table').getElementsByTagName('tbody')[0];
            proxyTable.innerHTML = '';

            const sortedProxies = Object.entries(proxies).sort((a, b) => {
                function score(v) {
                    const tests = ['tcp_connect', 'socks5_handshake', 'remote_connect', 'dns_ok', 'http_ok', 'https_ok', 'http_proxy_ok', 'https_proxy_ok'];
                    const passCount = tests.reduce((n, k) => n + (v[k] ? 1 : 0), 0);
                    const allPass = passCount === tests.length ? 2 : (passCount > 0 ? 1 : 0);
                    const bandwidth = v.bandwidth_kbps || 0;
                    const trackerScore = ((v.tracker_tcp_ok ? 1 : 0) + (v.tracker_udp_ok ? 1 : 0));
                    return [allPass, trackerScore, passCount, bandwidth];
                }
                const av = score(a[1]), bv = score(b[1]);
                for (let i = 0; i < av.length; ++i) {
                    if (bv[i] !== av[i]) return bv[i] - av[i];
                }
                return 0;
            });

            const MAX_ROWS = 1000;
            sortedProxies.slice(0, MAX_ROWS).forEach(([proxy, details], index) => {
                const row = proxyTable.insertRow(index);
                row.innerHTML = `
                    <td>${proxy}</td>
                    <td>${iconCell(details.tcp_connect)}</td>
                    <td>${iconCell(details.socks5_handshake)}</td>
                    <td>${iconCell(details.remote_connect)}</td>
                    <td>${iconCell(details.dns_ok)}</td>
                    <td>${iconCell(details.http_ok)} <small>(S5)</small></td>
                    <td>${iconCell(details.https_ok)} <small>(S5)</small></td>
                    <td>${iconCell(details.http_proxy_ok)}</td>
                    <td>${iconCell(details.https_proxy_ok)}</td>
                    <td>${details.bandwidth_kbps !== null ? details.bandwidth_kbps : ''}</td>
                    <td>${iconCell(details.tracker_tcp_ok)}</td>
                    <td>${iconCell(details.tracker_udp_ok)}</td>
                    <td>${details.last_checked ? details.last_checked : 'Never'}</td>
                    <td>
                        <button onclick="setProxyQB('${proxy}', ${index})">Set (qB)</button>
                        <button onclick="setProxyFF('${proxy}', ${index})">Set (FF)</button>
                        <button onclick="retestProxy('${proxy}', ${index})">Retest</button>
                    </td>
                `;
            });

            document.getElementById('last-update').innerText = `Last update: ${lastUpdate}`;
            enableColumnSorting();

            // Re-apply sort if active
            if (currentSort.idx !== null) {
                sortTable(currentSort.idx, currentSort.asc);
            }
        })
        .catch(error => {
            console.error('Error:', error);
        });
}

function retestProxy(proxy, rowIndex) {
    fetch(`/retest_proxy/${proxy}`)
        .then(response => response.json())
        .then(() => fetchProxies())
        .catch(error => {
            console.error('Error:', error);
            alert('An error occurred while retesting the proxy.');
        });
}

function updateCurrentProxies() {
    fetch('/current_proxy')
        .then(response => response.json())
        .then(data => {
            document.getElementById('current-proxy').innerText = data.current_proxy;
        })
        .catch(error => console.error('Error fetching qB proxy:', error));

    fetch('/current_firefox_proxy')
        .then(response => response.json())
        .then(data => {
            document.getElementById('current-firefox-proxy').innerText = data.firefox_proxy;
        })
        .catch(error => console.error('Error fetching Firefox proxy:', error));
}

function fetchStatus() {
    fetch('/update_status')
        .then(response => response.json())
        .then(data => {
            document.getElementById('update-status').innerText = data.status;
        })
        .catch(error => {
            console.error('Error:', error);
        });
}

function fetchQbConnectionStatus() {
    fetch('/qb_connection_status')
        .then(response => response.json())
        .then(data => {
            let status = document.getElementById('qb-connection-status');
            if (!status) {
                status = document.createElement('div');
                status.id = 'qb-connection-status';
                document.querySelector('.container').appendChild(status);
            }
            status.innerText = `qBittorrent Proxy Status: ${data.status}`;
        })
        .catch(error => {
            console.error('Error:', error);
        });
}

function fetchProgress() {
    fetch('/progress')
        .then(response => response.json())
        .then(data => {
            let progressElem = document.getElementById('proxy-progress');
            if (!progressElem) {
                progressElem = document.createElement('div');
                progressElem.id = 'proxy-progress';
                document.querySelector('.container').insertBefore(progressElem, document.querySelector('.table-container'));
            }
            if (data.current_proxy) {
                progressElem.innerText = `Testing proxy ${data.current_index} of ${data.total}: ${data.current_proxy}`;
            } else {
                progressElem.innerText = '';
            }
        })
        .catch(error => {
            console.error('Error:', error);
        });
}

function startProxyUpdates(interval) {
    fetchProxies();
    updateCurrentProxies();
    setInterval(fetchProxies, interval);
    setInterval(updateCurrentProxies, 15000);
    setInterval(fetchStatus, 1000);
    setInterval(fetchQbConnectionStatus, 300000);
    setInterval(fetchProgress, 1000);
}

function enableColumnSorting() {
    const table = document.getElementById('proxy-table');
    if (!table) return;
    const ths = table.querySelectorAll('th');

    ths.forEach((th, idx) => {
        th.style.cursor = 'pointer';
        th.onclick = function() {
            if (currentSort.idx === idx) currentSort.asc = !currentSort.asc;
            else { currentSort.idx = idx; currentSort.asc = false; }
            sortTable(idx, currentSort.asc);
        };
    });
}

function sortTable(colIdx, asc) {
    const table = document.getElementById('proxy-table');
    const tbody = table.tBodies[0];
    const rows = Array.from(tbody.rows);

    rows.sort((a, b) => {
        let v1 = a.cells[colIdx].textContent.trim();
        let v2 = b.cells[colIdx].textContent.trim();
        if ([1,2,3,4,5,6,7,8,10,11].includes(colIdx)) {
            const testScore = t => t.includes('✔') ? 2 : t.includes('✖') ? 1 : 0;
            v1 = testScore(v1); v2 = testScore(v2);
        }
        if (colIdx === 9) { 
            v1 = parseFloat(v1) || 0; 
            v2 = parseFloat(v2) || 0;
        }
        if (!isNaN(v1) && !isNaN(v2)) return asc ? v1 - v2 : v2 - v1;
        return asc ? v1.localeCompare(v2) : v2.localeCompare(v1);
    });

    rows.forEach(row => tbody.appendChild(row));
}

document.addEventListener('DOMContentLoaded', function() {
    startProxyUpdates(5000);
});
