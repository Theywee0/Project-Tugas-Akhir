// ==========================================
// File: static/js/charts.js
// ==========================================

document.addEventListener('DOMContentLoaded', function() {
    // 1. Dashboard - Grafik Konsumsi BBM
    if (window.dashboardChartData && window.dashboardChartData.labelsBBM) {
        const labelsBBM = window.dashboardChartData.labelsBBM;
        const dataBBM = window.dashboardChartData.dataBBM;
        
        new Chart(document.getElementById('chartBBM'), {
            type: 'bar',
            data: { labels: labelsBBM, datasets: [{ data: dataBBM,
                backgroundColor: labelsBBM.map((_, i) => i === labelsBBM.length - 1 ? '#1a472a' : '#a8d5b5'),
                borderRadius: 6, borderSkipped: false }] },
            options: { responsive: true, plugins: { legend: { display: false } },
                scales: { y: { grid: { color: '#f0f0f0' }, ticks: { font: { size: 11 } } }, x: { grid: { display: false }, ticks: { font: { size: 11 } } } } }
        });
    }

    // 2. Dashboard - Grafik Klaster (Doughnut)
    if (window.dashboardChartData && window.dashboardChartData.klasterLabels) {
        const klasterLabels = window.dashboardChartData.klasterLabels;
        const klasterData = window.dashboardChartData.klasterData;
        const klasterColors = ['#27ae60','#f39c12','#e74c3c','#3498db','#9b59b6'];
        
        const totalKlaster = klasterData.reduce((a,b)=>a+b, 0);
        new Chart(document.getElementById('chartKlaster'), {
            type: 'doughnut',
            data: { labels: klasterLabels, datasets: [{ data: klasterData.map(v => v || 0.01),
                backgroundColor: klasterColors, borderWidth: 0, hoverOffset: 4 }] },
            options: { cutout: '68%', responsive: true, plugins: { legend: { display: false },
                tooltip: { callbacks: { label: ctx => ` ${ctx.label}: ${klasterData[ctx.dataIndex]} unit` } } } },
            plugins: [{ id: 'centerText', beforeDraw(chart) {
                const { ctx, chartArea: { top, left, width, height } } = chart; ctx.save();
                ctx.font = 'bold 18px Segoe UI'; ctx.fillStyle = '#1f2933'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
                ctx.fillText(totalKlaster, left + width/2, top + height/2 - 8);
                ctx.font = '11px Segoe UI'; ctx.fillStyle = '#888'; ctx.fillText('unit', left + width/2, top + height/2 + 10); ctx.restore();
            } }]
        });
    }

    // 3. Helper filter klaster (dashboard)
    window.filterTable = function() {
        const filter = document.getElementById('filterKlaster').value;
        document.querySelectorAll('#tabelKendaraan tbody tr').forEach(row => {
            row.style.display = (!filter || row.dataset.klaster === filter) ? '' : 'none';
        });
    };
});
