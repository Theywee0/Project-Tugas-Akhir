from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from flask_mysqldb import MySQL
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
from models import normalisasi_periode, periode_clause, PERIODE_LABEL

auth_bp = Blueprint('auth', __name__)

# ===== Import mysql dari app =====
def get_mysql():
    from app import mysql
    return mysql


def _is_hashed(stored):
    """True jika password tersimpan sudah berbentuk hash werkzeug (mis. 'scrypt:...$...$...'
    atau 'pbkdf2:...$...$...'). Password teks biasa tidak punya pola 'metode$...'."""
    return bool(stored) and '$' in stored and ':' in stored.split('$', 1)[0]


# ===================================================
# DECORATOR: Proteksi halaman (wajib login)
# ===================================================
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Silakan login terlebih dahulu.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Silakan login terlebih dahulu.', 'warning')
            return redirect(url_for('auth.login'))
        if session.get('role') != 'admin':
            flash('Akses ditolak. Halaman ini khusus Admin IT.', 'danger')
            return redirect(url_for('auth.dashboard_driver'))
        return f(*args, **kwargs)
    return decorated

def kepala_gs_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Silakan login terlebih dahulu.', 'warning')
            return redirect(url_for('auth.login'))
        if session.get('role') != 'kepala_operasional_gs':
            flash('Akses ditolak. Halaman ini hanya untuk Kepala Operasional GS.', 'danger')
            return redirect(url_for('auth.dashboard_driver'))
        return f(*args, **kwargs)
    return decorated

def driver_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Silakan login terlebih dahulu.', 'warning')
            return redirect(url_for('auth.login'))
        if session.get('role') != 'driver':
            flash('Akses ditolak. Halaman ini hanya untuk Driver.', 'danger')
            return redirect(url_for('auth.dashboard_driver')) # redirect to driver if not driver? Wait, that's what was there before
        return f(*args, **kwargs)
    return decorated


# ===================================================
# LOGIN
# ===================================================
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    # Kalau sudah login, langsung redirect
    if 'user_id' in session:
        if session['role'] in ['admin', 'kepala_operasional_gs']:
            return redirect(url_for('laporan.dashboard_admin'))
        return redirect(url_for('auth.dashboard_driver'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        # Validasi input kosong
        if not username or not password:
            flash('Username dan password wajib diisi.', 'danger')
            return render_template('auth/login.html')

        # Cek user di database
        mysql = get_mysql()
        cur = mysql.connection.cursor()
        cur.execute("SELECT Id_User, Nama, Username, Password, Role, is_first_login FROM user WHERE Username = %s", (username,))
        user = cur.fetchone()

        valid = False
        if user:
            stored = user[3] or ''
            if _is_hashed(stored):
                valid = check_password_hash(stored, password)
            elif stored == password:
                valid = True
                cur.execute("UPDATE user SET Password=%s WHERE Id_User=%s",
                            (generate_password_hash(password), user[0]))
                mysql.connection.commit()
        cur.close()

        if valid:
            is_first_login = user[5]
            if is_first_login == 1:
                # Sesi sementara khusus untuk ganti password
                session['force_change_uid'] = user[0]
                session['force_change_nama'] = user[1]
                return redirect(url_for('auth.force_change'))

            # Login berhasil - simpan ke session
            session['user_id']  = user[0]
            session['nama']     = user[1]
            session['username'] = user[2]
            session['role']     = user[4]

            flash(f'Selamat datang, {user[1]}!', 'success')

            # Arahkan sesuai role
            if user[4] in ['admin', 'kepala_operasional_gs']:
                return redirect(url_for('laporan.dashboard_admin'))
            else:
                return redirect(url_for('auth.dashboard_driver'))
        else:
            flash('Username atau password salah.', 'danger')

    return render_template('auth/login.html')


# ===================================================
# FORCE CHANGE PASSWORD
# ===================================================
@auth_bp.route('/force-change', methods=['GET', 'POST'])
def force_change():
    if 'force_change_uid' not in session:
        return redirect(url_for('auth.login'))
        
    if request.method == 'POST':
        password_baru = request.form.get('PasswordBaru')
        konfirmasi = request.form.get('KonfirmasiPassword')
        
        import re
        if not password_baru or not konfirmasi:
            flash('Semua kolom wajib diisi.', 'danger')
            return redirect(url_for('auth.force_change'))
            
        if password_baru != konfirmasi:
            flash('Password baru dan konfirmasi tidak cocok.', 'danger')
            return redirect(url_for('auth.force_change'))
            
        if len(password_baru) < 8 or not re.search(r'[A-Z]', password_baru) or not re.search(r'[!@#$%^&*(),.?":{}|<>]', password_baru):
            flash('Password baru tidak memenuhi syarat keamanan.', 'danger')
            return redirect(url_for('auth.force_change'))
            
        mysql = get_mysql()
        cur = mysql.connection.cursor()
        hashed = generate_password_hash(password_baru)
        
        cur.execute("UPDATE user SET Password=%s, is_first_login=0 WHERE Id_User=%s", (hashed, session['force_change_uid']))
        
        # Ambil data user lengkap untuk login session
        cur.execute("SELECT Id_User, Nama, Username, Role FROM user WHERE Id_User=%s", (session['force_change_uid'],))
        u = cur.fetchone()
        mysql.connection.commit()
        cur.close()
        
        # Clear the temporary force change session
        session.pop('force_change_uid', None)
        session.pop('force_change_nama', None)
        
        # Buat session login penuh
        session['user_id'] = u[0]
        session['nama'] = u[1]
        session['username'] = u[2]
        session['role'] = u[3]
        
        flash('Password berhasil diubah. Selamat datang!', 'success')
        
        if u[3] in ['admin', 'kepala_operasional_gs']:
            return redirect(url_for('laporan.dashboard_admin'))
        else:
            return redirect(url_for('auth.dashboard_driver'))
            
    return render_template('auth/force_change.html')


# ===================================================
# LOGOUT
# ===================================================
@auth_bp.route('/logout')
def logout():
    nama = session.get('nama', 'Pengguna')
    session.clear()
    flash(f'Sampai jumpa, {nama}! Anda telah logout.', 'info')
    return redirect(url_for('auth.login'))


# ===================================================
# DASHBOARD DRIVER
# ===================================================
@auth_bp.route('/dashboard/driver')
@login_required
def dashboard_driver():
    """Dashboard driver dengan ringkasan data nyata.

    Ketiga kartu statistik (Perjalanan, BBM, Total Jarak) dikendalikan oleh
    SATU filter periode yang sama (Hari/Minggu/Bulan/Tahun Ini), sehingga
    saat periode diganti, ketiganya berubah bersamaan mengikuti rentang
    waktu yang identik. Klausa periode dibangun terpusat di models.
    """
    periode = normalisasi_periode(request.args.get('periode'))
    # Satu klausa tanggal yang sama dipakai untuk KETIGA query di bawah.
    cond = periode_clause(periode, 'Tanggal')

    mysql = get_mysql()
    cur = mysql.connection.cursor()

    # Cari Id_Driver milik user yang login
    cur.execute("SELECT Id_Driver FROM driver WHERE Id_User = %s", (session['user_id'],))
    row = cur.fetchone()
    id_driver = row[0] if row else None

    stats = {'perjalanan': 0, 'bbm': 0.0, 'total_jarak': 0.0}
    # Default agar variabel selalu terdefinisi walau driver belum punya data.
    pending = {'perjalanan': 0, 'bbm': 0, 'maintenance': 0, 'inspeksi': 0, 'total': 0}
    aktivitas = []
    if id_driver:
        # Jumlah perjalanan pada periode terpilih
        cur.execute(
            f"SELECT COUNT(*) FROM perjalanan WHERE ID_Driver = %s AND {cond}",
            (id_driver,))
        stats['perjalanan'] = int(cur.fetchone()[0])

        # Total liter BBM pada periode terpilih
        cur.execute(
            f"SELECT COALESCE(SUM(Jumlah_BBM), 0) FROM pengisian_bbm WHERE Id_Driver = %s AND {cond}",
            (id_driver,))
        stats['bbm'] = float(cur.fetchone()[0])

        # Total jarak tempuh pada periode terpilih
        cur.execute(
            f"SELECT COALESCE(SUM(Jumlah_KM), 0) FROM perjalanan WHERE ID_Driver = %s AND {cond}",
            (id_driver,))
        stats['total_jarak'] = float(cur.fetchone()[0])

        # E — Data MILIK driver yang masih 'Belum' diverifikasi (lintas periode),
        # sebagai pengingat agar dikoreksi sebelum dikunci admin. COUNT read-only.
        for key, tabel, kol in [('perjalanan', 'perjalanan', 'ID_Driver'),
                                ('bbm', 'pengisian_bbm', 'Id_Driver'),
                                ('maintenance', 'maintenance', 'ID_Driver'),
                                ('inspeksi', 'inspeksi', 'ID_Driver')]:
            cur.execute(f"SELECT COUNT(*) FROM {tabel} WHERE {kol} = %s AND Status_Verifikasi = 'Belum'",
                        (id_driver,))
            pending[key] = int(cur.fetchone()[0])
        pending['total'] = pending['perjalanan'] + pending['bbm'] + pending['maintenance'] + pending['inspeksi']

        # F — Aktivitas terbaru milik driver (gabungan 4 modul, 5 terbaru).
        cur.execute("""
            SELECT akt.tgl, akt.jenis, akt.nopol, akt.status FROM (
                SELECT p.Tanggal AS tgl, p.Jam AS jam, 'Perjalanan' AS jenis,
                       k.No_Polisi AS nopol, p.Status_Verifikasi AS status
                FROM perjalanan p LEFT JOIN kendaraan k ON p.ID_Kendaraan = k.ID_Kendaraan
                WHERE p.ID_Driver = %s
                UNION ALL
                SELECT b.Tanggal, b.Jam, 'Pengisian BBM', k.No_Polisi, b.Status_Verifikasi
                FROM pengisian_bbm b LEFT JOIN kendaraan k ON b.Id_Kendaraan = k.ID_Kendaraan
                WHERE b.Id_Driver = %s
                UNION ALL
                SELECT m.Tanggal, NULL, 'Maintenance', k.No_Polisi, m.Status_Verifikasi
                FROM maintenance m LEFT JOIN kendaraan k ON m.ID_Kendaraan = k.ID_Kendaraan
                WHERE m.ID_Driver = %s
                UNION ALL
                SELECT i.Tanggal, NULL, 'Inspeksi', k.No_Polisi, i.Status_Verifikasi
                FROM inspeksi i LEFT JOIN kendaraan k ON i.ID_Kendaraan = k.ID_Kendaraan
                WHERE i.ID_Driver = %s
            ) akt
            ORDER BY akt.tgl DESC, akt.jam DESC
            LIMIT 5
        """, (id_driver, id_driver, id_driver, id_driver))
        aktivitas = cur.fetchall()

    cur.close()
    return render_template('dashboard_driver.html',
        stats=stats, periode=periode,
        periode_label=PERIODE_LABEL[periode], periode_opsi=PERIODE_LABEL,
        pending=pending, aktivitas=aktivitas)