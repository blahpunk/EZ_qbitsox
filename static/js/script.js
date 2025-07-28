function setProxy(proxy, rowIndex) {
    fetch(`/set_proxy/${proxy}`)
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                fetch('/current_proxy')
                    .then(response => response.json())
                    .then(data => {
                        document.getElementById('current-proxy').innerText = data.current_proxy;
                    });
                alert(`Proxy set to ${proxy}`);
                fetchQbConnectionStatus();  // Update the qBittorrent connection status
            } else {
                alert('Failed to set proxy.');
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('An error occurred while setting the proxy.');
        });
}

function updateProxies() {
    const proxyTable = document.getElementById('proxy-table').getElementsByTagName('tbody')[0];
    proxyTable.innerHTML = '';  // Clear the table
    const loadingRow = proxyTable.insertRow(0);
    loadingRow.innerHTML = `<td colspan="4">Updating proxies, please wait...</td>`;

    fetch('/update_proxies')
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                alert('Proxies updated successfully!');
                fetchProxies();  // Refresh the proxy list after updating
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
            proxyTable.innerHTML = '';  // Clear the table

            const sortedProxies = Object.entries(proxies).sort((a, b) => {
                const statusOrder = { "Active": 1, "Inactive": 2, "Unknown": 3 };
                return statusOrder[a[1].status] - statusOrder[b[1].status];
            });

            sortedProxies.forEach(([proxy, details], index) => {
                const statusClass = details.status === 'Active' ? 'status-active' :
                                   details.status === 'Inactive' ? 'status-inactive' :
                                   'status-unknown';
                row = proxyTable.insertRow(index);
                row.innerHTML = `
                    <td>${proxy}</td>
                    <td id="status-${index}" class="${statusClass}">${details.status}</td>
                    <td>${details.last_checked ? details.last_checked : 'Never'}</td>
                    <td>
                        <button onclick="setProxy('${proxy}', ${index})">Set as Proxy</button>
                        <button onclick="retestProxy('${proxy}', ${index})">Retest</button>
                    </td>
                `;
            });

            document.getElementById('last-update').innerText = `Last update: ${lastUpdate}`;
        })
        .catch(error => {
            console.error('Error:', error);
        });
}

function retestProxy(proxy, rowIndex) {
    fetch(`/retest_proxy/${proxy}`)
        .then(response => response.json())
        .then(data => {
            const statusCell = document.getElementById(`status-${rowIndex}`);
            statusCell.innerText = data.status;
            statusCell.className = data.status === 'Active' ? 'status-active' :
                                  data.status === 'Inactive' ? 'status-inactive' :
                                  'status-unknown';
        })
        .catch(error => {
            console.error('Error:', error);
            alert('An error occurred while retesting the proxy.');
        });
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
    fetchProxies();  // Initial load
    setInterval(fetchProxies, interval);
    setInterval(fetchStatus, 1000);  // Update status every second
    setInterval(fetchQbConnectionStatus, 300000);  // Update qBittorrent connection status every 5 minutes
    setInterval(fetchProgress, 1000); // Poll progress every second
}

startProxyUpdates(5000);
