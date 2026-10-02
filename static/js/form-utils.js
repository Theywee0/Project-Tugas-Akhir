// Global Form Utilities Extracted & Cleaned

// Hitung jumlah baris pada textarea
function hitungBaris(idArea, idCounter) {
    const area = document.getElementById(idArea);
    const counter = document.getElementById(idCounter);
    if(area && counter) {
        counter.textContent = area.value.split('\n').filter(l => l.trim() !== '').length;
    }
}

// Preview gambar sebelum upload
function previewFoto(input, id) {
    const p = document.getElementById(id);
    if (input.files && input.files[0] && p) {
        const r = new FileReader();
        r.onload = e => { p.src = e.target.result; p.style.display = 'block'; };
        r.readAsDataURL(input.files[0]);
    }
}

// Toggle password visibility
function togglePassword() {
    const field = document.getElementById('passwordField') || document.getElementById('password');
    const icon = document.getElementById('eyeIcon');
    if (field) {
        field.type = field.type === 'password' ? 'text' : 'password';
        if (icon) {
            if (field.type === 'text') icon.classList.replace('bi-eye', 'bi-eye-slash');
            else icon.classList.replace('bi-eye-slash', 'bi-eye');
        }
    }
}

// Hitung jarak KM otomatis
function hitungKM() {
    const elAwal = document.getElementById('kmAwal');
    const elAkhir = document.getElementById('kmAkhir');
    const elHasil = document.getElementById('hasilKM');
    
    if (elAwal && elAkhir && elHasil) {
        const a = parseFloat(elAwal.value) || 0;
        const b = parseFloat(elAkhir.value) || 0;
        
        // Memaksa validasi HTML5 agar KM Akhir tidak bisa lebih kecil dari KM Awal
        // (Berlaku untuk BBM dan Perjalanan)
        if (a > 0) {
            elAkhir.min = a;
        } else {
            elAkhir.min = 0;
        }

        elHasil.textContent = (b > a ? (b - a).toFixed(1) : 0) + ' km';
    }
}

// Isi dropdown jenis BBM berdasarkan data dari select Kendaraan
function isiJenisBBM(currentVal = null) {
    const s = document.getElementById('selKendaraan');
    const bs = document.getElementById('selJenisBBM');
    if (!s || !bs) return;
    
    const o = s.options[s.selectedIndex];
    bs.innerHTML = '<option value="">-- Pilih Jenis BBM --</option>';
    
    if (s.value !== "") {
        ['bbm1','bbm2','bbm3'].forEach(k => {
            const v = o.dataset[k];
            if(v && v !== 'None' && v.trim() !== '') {
                bs.innerHTML += `<option value="${v}">${v}</option>`;
            }
        });
    }

    if(currentVal && currentVal !== 'None' && currentVal.trim() !== '') {
        // Jika currentVal tidak ada di options, tambahkan
        if(![...bs.options].some(x => x.value === currentVal)) {
            bs.innerHTML += `<option value="${currentVal}">${currentVal}</option>`;
        }
        bs.value = currentVal;
    }

    if(o) {
        const maxBBM = o.dataset.kapasitas;
        const inputBBM = document.querySelector('input[name="Jumlah_BBM"]');
        if(inputBBM) {
            if(maxBBM) {
                inputBBM.max = maxBBM;
                inputBBM.placeholder = `Maks: ${maxBBM} Liter`;
            } else {
                inputBBM.removeAttribute('max');
                inputBBM.placeholder = 'cth: 40';
            }
            
            // Translasi pesan validasi bawaan browser ke Bahasa Indonesia
            inputBBM.oninvalid = function() {
                if (this.validity.rangeOverflow) {
                    this.setCustomValidity('Tidak bisa mengisi lebih dari kapasitas tangki (' + this.max + ' Liter).');
                } else if (this.validity.valueMissing) {
                    this.setCustomValidity('Mohon isi jumlah BBM.');
                } else {
                    this.setCustomValidity('');
                }
            };
            inputBBM.oninput = function() {
                this.setCustomValidity('');
            };
        }
    }
}

// Auto-fill KM Awal via API berdasarkan ID kendaraan
function isiKmAwal() {
    const sel = document.getElementById('selKendaraan');
    const kmAwal = document.getElementById('kmAwal');
    const hint = document.getElementById('kmAwalHint');
    
    if (!sel || !kmAwal || !hint) return;
    
    const id = sel.value;
    if(!id) {
        kmAwal.value = '';
        kmAwal.readOnly = true;
        hint.innerHTML = '<i class="bi bi-info-circle me-1"></i>Pilih kendaraan dulu — terisi otomatis';
        hitungKM();
        return;
    }
    
    hint.innerHTML = '<i class="bi bi-arrow-repeat me-1"></i>Memuat KM terakhir...';
    fetch(`/api/kendaraan/${id}/km-terakhir`)
        .then(r => r.json())
        .then(d => {
            const km = parseFloat(d.km_terakhir) || 0;
            if(km > 0) {
                kmAwal.value = km;
                kmAwal.readOnly = true;
                hint.innerHTML = '<i class="bi bi-check-circle me-1 text-success"></i>Otomatis dari KM terakhir kendaraan';
            } else {
                kmAwal.value = '';
                kmAwal.readOnly = false;
                hint.innerHTML = '<i class="bi bi-pencil me-1"></i>Belum ada riwayat KM — isi manual';
            }
            hitungKM();
        })
        .catch(() => {
            kmAwal.readOnly = false;
            hint.innerHTML = '<i class="bi bi-exclamation-triangle me-1 text-warning"></i>Gagal memuat — isi manual';
        });
}

// Auto-fill KM Kendaraan (Mirip isiKmAwal tapi beda ID element)
function isiKmKendaraan() {
    const sel = document.getElementById('selKendaraan');
    const km = document.getElementById('kmKendaraan');
    const hint = document.getElementById('kmHint');
    
    if (!sel || !km || !hint) return;
    
    const id = sel.value;
    if(!id) {
        km.value = '';
        km.readOnly = true;
        hint.innerHTML = '<i class="bi bi-info-circle me-1"></i>Terisi otomatis dari KM terakhir';
        return;
    }
    
    hint.innerHTML = '<i class="bi bi-arrow-repeat me-1"></i>Memuat KM terakhir...';
    fetch(`/api/kendaraan/${id}/km-terakhir`)
        .then(r => r.json())
        .then(d => {
            const v = parseFloat(d.km_terakhir) || 0;
            if(v > 0) {
                km.value = v;
                km.readOnly = true;
                hint.innerHTML = '<i class="bi bi-check-circle me-1 text-success"></i>Otomatis dari KM terakhir kendaraan';
            } else {
                km.value = '';
                km.readOnly = false;
                hint.innerHTML = '<i class="bi bi-pencil me-1"></i>Belum ada riwayat KM — isi manual';
            }
        })
        .catch(() => {
            km.readOnly = false;
            hint.innerHTML = '<i class="bi bi-exclamation-triangle me-1 text-warning"></i>Gagal memuat — isi manual';
        });
}

// Inisialisasi saat halaman selesai dimuat
window.addEventListener('load', () => {
    // Isi Tanggal dan Jam otomatis jika elemennya ada dan kosong
    const t = document.querySelector('[name=Tanggal]');
    const j = document.querySelector('[name=Jam]');
    const n = new Date();
    
    if(t && !t.value) {
        t.value = n.toISOString().split('T')[0];
    }
    if(j && !j.value) {
        j.value = n.toTimeString().slice(0,5);
    }
    
    // Panggil hitungKM agar kotak hijau langsung terisi di halaman Edit
    hitungKM();
    
    // Inisialisasi line counter jika berada di halaman yang butuh itu
    if(document.getElementById('txtKeluhan')) hitungBaris('txtKeluhan','ctrKeluhan');
    if(document.getElementById('txtSpare')) hitungBaris('txtSpare','ctrSpare');
});

// Auto-fill KM Awal KHUSUS BBM via API berdasarkan ID kendaraan
function isiKmBbmAwal() {
    const sel = document.getElementById("selKendaraan");
    const kmAwal = document.getElementById("kmAwal");
    const hint = document.getElementById("kmAwalHint");
    
    if (!sel || !kmAwal || !hint) return;
    
    const id = sel.value;
    if(!id) {
        kmAwal.value = "";
        kmAwal.readOnly = true;
        hint.innerHTML = "<i class=\"bi bi-info-circle me-1\"></i>Pilih kendaraan dulu \u2014 terisi otomatis";
        hitungKM();
        return;
    }
    
    hint.innerHTML = "<i class=\"bi bi-arrow-repeat me-1\"></i>Memuat nota BBM terakhir...";
    fetch(`/api/kendaraan/${id}/km-bbm-terakhir`)
        .then(r => r.json())
        .then(d => {
            const km = parseFloat(d.km_bbm_terakhir) || 0;
            if(km > 0) {
                kmAwal.value = km;
                kmAwal.readOnly = true;
                hint.innerHTML = "<i class=\"bi bi-check-circle-fill text-success me-1\"></i>Ditarik dari riwayat isi bensin terakhir";
            } else {
                kmAwal.value = "";
                kmAwal.readOnly = false;
                hint.innerHTML = "<i class=\"bi bi-pencil me-1\"></i>BBM Perdana: Ketik manual KM saat isi BBM sebelumnya";
            }
            hitungKM();
        })
        .catch(e => {
            console.error("Gagal load KM BBM:", e);
            kmAwal.readOnly = false;
            hint.innerHTML = "<i class=\"bi bi-exclamation-triangle text-danger me-1\"></i>Gagal memuat. Ketik manual.";
        });
}

