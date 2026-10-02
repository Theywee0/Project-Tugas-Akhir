function toggleSidebar() {
    document.getElementById('appSidebar').classList.toggle('open');
    document.getElementById('sidebarBackdrop').classList.toggle('show');
    document.body.classList.toggle('sidebar-open');
}
// Loading state pada submit form
document.addEventListener('submit', function (e) {
    const btn = e.target.querySelector('button[type=submit]');
    if (btn && !btn.classList.contains('btn-loading')) {
        btn.classList.add('btn-loading');
        btn.insertAdjacentHTML('afterbegin', '<span class="spinner-border spinner-border-sm me-2"></span>');
    }
});
// Searchable combobox generik (.searchable-select): nilai yang dikirim tetap
// di input hidden, label rich hanya untuk tampilan & pencarian.
document.querySelectorAll('.searchable-select').forEach(function (ss) {
    const hidden = ss.querySelector('input[type=hidden]');
    const display = ss.querySelector('.ss-input');
    const panel = ss.querySelector('.ss-panel');
    const search = ss.querySelector('.ss-search');
    const list = ss.querySelector('.ss-list');
    const items = Array.from(ss.querySelectorAll('.ss-item'));
    const empty = document.createElement('div');
    empty.className = 'ss-empty'; empty.textContent = 'Tidak ada perjalanan yang cocok.'; empty.style.display = 'none';
    list.appendChild(empty);
    function setFrom(val) {
        const it = items.find(i => i.dataset.value === String(val));
        display.value = (it && val !== '') ? it.dataset.text : (val !== '' && val != null ? ('#' + val) : '');
    }
    setFrom(hidden.value || '');
    function open() { panel.classList.add('show'); search.value = ''; items.forEach(i => i.style.display = ''); empty.style.display = 'none'; setTimeout(() => search.focus(), 0); }
    function close() { panel.classList.remove('show'); }
    display.addEventListener('click', function (e) { e.stopPropagation(); panel.classList.contains('show') ? close() : open(); });
    search.addEventListener('input', function () {
        const q = search.value.toLowerCase(); let n = 0;
        items.forEach(i => {
            const ok = i.dataset.value === '' || i.dataset.text.toLowerCase().includes(q);
            i.style.display = ok ? '' : 'none';
            if (ok && i.dataset.value !== '') n++;
        });
        empty.style.display = (n === 0) ? 'block' : 'none';
    });
    items.forEach(i => i.addEventListener('click', function () { hidden.value = i.dataset.value; display.value = i.dataset.value ? i.dataset.text : ''; close(); }));
    document.addEventListener('click', function (e) { if (!ss.contains(e.target)) close(); });
});
// Toggle kondisi inspeksi (segmented button): tampilkan Keterangan & Foto hanya
// saat "Tidak Normal", dan jadikan Keterangan wajib. required di-toggle via JS
// agar field tersembunyi tidak memblokir submit (hindari "not focusable").
document.querySelectorAll('.komponen-card[data-field]').forEach(function (card) {
    const radios = card.querySelectorAll('.kondisi-radio');
    const detail = card.querySelector('.detail-tn');
    const ket = detail ? detail.querySelector('.ket-input') : null;
    function sync() {
        const tnRadio = card.querySelector('.kondisi-radio[value="Tidak Normal"]');
        const tn = !!(tnRadio && tnRadio.checked);
        if (detail) detail.style.display = tn ? 'block' : 'none';
        if (ket) ket.required = tn;   // Keterangan wajib saat Tidak Normal
    }
    radios.forEach(r => r.addEventListener('change', sync));
    sync();
});
// Ambil Lokasi Otomatis (Geolocation API): isi field Koordinat (readonly) dengan
// "latitude, longitude". Bila izin ditolak / gagal, tampilkan pesan informatif saja.
document.querySelectorAll('.koordinat-gps').forEach(function (kg) {
    const input = kg.querySelector('.kg-input');
    const btn = kg.querySelector('.kg-btn');
    const msg = kg.querySelector('.kg-msg');
    btn.addEventListener('click', function () {
        if (!navigator.geolocation) {
            msg.innerHTML = '<i class="bi bi-exclamation-triangle me-1 text-warning"></i>Perangkat atau browser tidak mendukung pengambilan lokasi (GPS).';
            return;
        }
        msg.innerHTML = '<i class="bi bi-arrow-repeat me-1"></i>Mengambil lokasi…';
        btn.disabled = true;
        navigator.geolocation.getCurrentPosition(function (pos) {
            input.value = pos.coords.latitude.toFixed(5) + ', ' + pos.coords.longitude.toFixed(5);
            msg.innerHTML = '<i class="bi bi-check-circle me-1 text-success"></i>Lokasi berhasil diambil.';
            btn.disabled = false;
        }, function (err) {
            let m = 'Gagal mengambil lokasi.';
            if (err.code === 1) m = 'Akses lokasi ditolak. Aktifkan izin lokasi pada browser untuk merekam koordinat.';
            else if (err.code === 2) m = 'Lokasi tidak tersedia saat ini.';
            else if (err.code === 3) m = 'Waktu pengambilan lokasi habis. Silakan coba lagi.';
            msg.innerHTML = '<i class="bi bi-exclamation-triangle me-1 text-warning"></i>' + m;
            btn.disabled = false;
        }, { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 });
    });
});

// Select2 Initialization
$(document).ready(function() {
    if ($.fn.select2) {
        $('.select2-searchable').each(function() {
            $(this).select2({
                theme: 'bootstrap-5',
                width: '100%',
                placeholder: $(this).data('placeholder') || 'Pilih salah satu...'
            });
        });
        
        // Add search placeholder dynamically based on data attribute
        $(document).on('select2:open', function(e) {
            let searchPlaceholder = $(e.target).data('search-placeholder') || 'Cari...';
            setTimeout(() => {
                let searchField = document.querySelector('.select2-search__field');
                if (searchField) {
                    searchField.setAttribute('placeholder', searchPlaceholder);
                }
            }, 0);
        });
    }
});

// Translasi Global Validasi HTML5 (Pesan Error) ke Bahasa Indonesia
document.addEventListener('invalid', function(e) {
    let el = e.target;
    // Abaikan jika elemen sudah punya kustom oninvalid sendiri (misal dari HTML/JS lain)
    if (el.hasAttribute('oninvalid') || typeof el.oninvalid === 'function') return;

    if (el.validity.valueMissing) {
        if (el.type === 'file') {
            el.setCustomValidity('Mohon pilih dan unggah sebuah file.');
        } else if (el.tagName.toLowerCase() === 'select') {
            el.setCustomValidity('Mohon pilih salah satu item dalam daftar.');
        } else if (el.type === 'checkbox' || el.type === 'radio') {
            el.setCustomValidity('Mohon centang opsi ini.');
        } else {
            el.setCustomValidity('Mohon isi kolom ini, tidak boleh kosong.');
        }
    } else if (el.validity.patternMismatch) {
        el.setCustomValidity(el.title ? el.title : 'Format data yang Anda masukkan tidak sesuai.');
    } else if (el.validity.typeMismatch && el.type === 'email') {
        el.setCustomValidity('Mohon masukkan alamat email yang benar.');
    } else if (el.validity.rangeUnderflow) {
        if (el.id === 'kmAkhir') {
            if (window.location.pathname.includes('bbm')) {
                el.setCustomValidity('Nilai tidak boleh kurang dari KM sebelum pengisian.');
            } else {
                el.setCustomValidity('Nilai tidak boleh kurang dari KM awal.');
            }
        } else {
            el.setCustomValidity('Nilai tidak boleh kurang dari ' + el.min + '.');
        }
    } else if (el.validity.rangeOverflow) {
        el.setCustomValidity('Nilai tidak boleh lebih dari ' + el.max + '.');
    } else {
        el.setCustomValidity('Data tidak valid.');
    }
}, true); // true = capture phase (karena event invalid tidak bubble)

// Menghapus pesan error ketika user mulai memperbaiki ketikan/pilihan
document.addEventListener('input', function(e) {
    if (e.target && e.target.setCustomValidity && !e.target.hasAttribute('oninvalid') && typeof e.target.oninvalid !== 'function') {
        e.target.setCustomValidity('');
    }
}, true);
document.addEventListener('change', function(e) {
    if (e.target && e.target.setCustomValidity && !e.target.hasAttribute('oninvalid') && typeof e.target.oninvalid !== 'function') {
        e.target.setCustomValidity('');
    }
}, true);
