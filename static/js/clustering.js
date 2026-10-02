// ==========================================
// File: static/js/clustering.js
// ==========================================
document.addEventListener('DOMContentLoaded', function() {
    if (!window.clusteringChartData) return;

    // 1. ELBOW CHART
    if (window.clusteringChartData.labels && window.clusteringChartData.labels.length > 0) {
        const ctxElbow = document.getElementById('chartElbow');
        if (ctxElbow) {
            new Chart(ctxElbow, {
                type: 'line',
                data: { 
                    labels: window.clusteringChartData.labels, 
                    datasets: [{ 
                        label: 'WCSS (Inertia)', 
                        data: window.clusteringChartData.wcss, 
                        borderColor: '#1a472a', 
                        backgroundColor: 'rgba(45,106,79,.12)', 
                        pointBackgroundColor: '#1a472a', 
                        pointRadius: 4, 
                        borderWidth: 2, 
                        fill: true, 
                        tension: 0.3 
                    }] 
                },
                options: { 
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { 
                        legend: { display: false }, 
                        tooltip: { 
                            callbacks: { 
                                title: items => 'k = ' + items[0].label, 
                                label: ctx => 'WCSS: ' + ctx.parsed.y 
                            } 
                        } 
                    },
                    scales: { 
                        x: { title: { display: true, text: 'Jumlah Cluster (k)', font: {size: 10} }, grid: { display: false }, ticks: {font: {size: 10}} }, 
                        y: { title: { display: false }, grid: { color: '#f0f0f0' }, ticks: {font: {size: 10}} } 
                    } 
                }
            });
        }
    }

    // 2. SCATTER CHART
    if (window.clusteringChartData.scatterRaw) {
        const scatterRaw = window.clusteringChartData.scatterRaw;
        const datasets = [];
        const colors = ['#27ae60', '#f39c12', '#e74c3c', '#2980b9', '#8e44ad', '#16a085', '#d35400', '#2c3e50'];
        let colorIndex = 0;
        
        for (const [kat, titik] of Object.entries(scatterRaw)) {
            if (titik.length === 0) continue;
            const color = colors[colorIndex % colors.length];
            datasets.push({ 
                label: kat, 
                data: titik.map(t => ({x: t.x, y: t.y, label: t.label})), 
                backgroundColor: color + 'cc', 
                borderColor: color, 
                pointRadius: 6, 
                pointHoverRadius: 8 
            });
            colorIndex++;
        }

        const ctxScatter = document.getElementById('chartScatter');
        if (ctxScatter) {
            new Chart(ctxScatter, {
                type: 'scatter',
                data: { datasets },
                options: { 
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { 
                        legend: { position: 'top', labels: { font: { size: 12 }, usePointStyle: true, boxWidth: 8 } }, 
                        tooltip: { callbacks: { label: ctx => ` ${ctx.raw.label}: Jarak=${ctx.raw.x.toFixed(0)} km, Rasio=${ctx.raw.y.toFixed(4)}` } } 
                    },
                    scales: { 
                        x: { title: { display: true, text: 'Total Jarak (km)' } }, 
                        y: { title: { display: true, text: 'Rasio Konsumsi (L/km)' } } 
                    } 
                }
            });
        }
    }

    // 3. PAGINATION & FILTER
    initTable();
});

// Table State
let currentPage = 1;
const rowsPerPage = 10;
let filteredRows = [];

function initTable() {
    const tableBody = document.getElementById('masterTableBody');
    if (!tableBody) return;
    
    // Get all rows
    const allRows = Array.from(tableBody.querySelectorAll('tr.data-row'));
    if (allRows.length === 0) return;

    // Save rows for filtering
    window.allTableRows = allRows;
    filterTable(); // Initial render
}

function filterTable() {
    const select = document.getElementById('filterCluster');
    if (!select || !window.allTableRows) return;
    
    const filterValue = select.value;
    
    // Hide all rows initially
    window.allTableRows.forEach(row => row.style.display = 'none');
    
    // Filter rows
    if (filterValue === 'Semua') {
        filteredRows = window.allTableRows;
    } else {
        filteredRows = window.allTableRows.filter(row => row.getAttribute('data-klaster') === filterValue);
    }
    
    // Update numbering
    filteredRows.forEach((row, index) => {
        row.querySelector('.row-num').textContent = index + 1;
    });

    currentPage = 1;
    renderPage();
    renderPagination();
}

function renderPage() {
    // Hide all filtered rows
    filteredRows.forEach(row => row.style.display = 'none');
    
    // Calculate bounds
    const start = (currentPage - 1) * rowsPerPage;
    const end = start + rowsPerPage;
    
    // Show rows for current page
    filteredRows.slice(start, end).forEach(row => {
        row.style.display = ''; // default table-row
    });
    
    // Update info text
    const info = document.getElementById('pageInfo');
    if (info) {
        if (filteredRows.length === 0) {
            info.textContent = 'Tidak ada data ditemukan.';
        } else {
            const actualEnd = Math.min(end, filteredRows.length);
            info.textContent = `Menampilkan ${start + 1} - ${actualEnd} dari ${filteredRows.length} data`;
        }
    }
}

function renderPagination() {
    const ul = document.getElementById('paginationUL');
    if (!ul) return;
    ul.innerHTML = '';
    
    const totalPages = Math.ceil(filteredRows.length / rowsPerPage);
    if (totalPages <= 1) return; // No pagination needed
    
    // Prev Button
    const liPrev = document.createElement('li');
    liPrev.className = `page-item ${currentPage === 1 ? 'disabled' : ''}`;
    liPrev.innerHTML = `<a class="page-link" href="#" onclick="changePage(${currentPage - 1}); return false;">&laquo;</a>`;
    ul.appendChild(liPrev);
    
    // Page Buttons
    for (let i = 1; i <= totalPages; i++) {
        const li = document.createElement('li');
        li.className = `page-item ${currentPage === i ? 'active' : ''}`;
        li.innerHTML = `<a class="page-link" href="#" onclick="changePage(${i}); return false;">${i}</a>`;
        ul.appendChild(li);
    }
    
    // Next Button
    const liNext = document.createElement('li');
    liNext.className = `page-item ${currentPage === totalPages ? 'disabled' : ''}`;
    liNext.innerHTML = `<a class="page-link" href="#" onclick="changePage(${currentPage + 1}); return false;">&raquo;</a>`;
    ul.appendChild(liNext);
}

window.changePage = function(page) {
    const totalPages = Math.ceil(filteredRows.length / rowsPerPage);
    if (page < 1 || page > totalPages) return;
    currentPage = page;
    renderPage();
    renderPagination();
};
