from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
from models import get_last_km, boleh_edit, set_status_verifikasi, STATUS_TERVERIFIKASI, field_kosong
import os
from routes.email_helper import kirim_notifikasi_background

perjalanan_bp = Blueprint('perjalanan', __name__)
UPLOAD_FOLDER = 'static/uploads/perjalanan'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

def allowed_file(f):
    return '.' in f and f.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_mysql():
    from app import mysql
    return mysql

def _fmt_time(v):
    """Format nilai TIME dari MySQL (timedelta) menjadi 'HH:MM' untuk input <input type=time>."""
    import datetime
    if isinstance(v, datetime.timedelta):
        total = int(v.total_seconds())
        return "%02d:%02d" % (total // 3600, (total % 3600) // 60)
    return str(v)[:5] if v else ''

def save_foto(file, prefix):
    if file and file.filename != '' and allowed_file(file.filename):
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        filename = secure_filename(f"{prefix}_{file.filename}")
        file.save(os.path.join(UPLOAD_FOLDER, filename))
        return filename
    return None

# =============================================
# LIST PERJALANAN
# =============================================
@perjalanan_bp.route('/perjalanan')
def list_perjalanan():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()

    # Kolom dienumerasi eksplisit (bukan p.*) agar indeks kolom join tetap stabil
    # meski tabel bertambah kolom status; Status_Verifikasi ditaruh di indeks 17.
    kolom = """
        p.ID_Perjalanan, p.Tanggal, p.Jam, p.ID_Driver, p.ID_Kendaraan,
        p.KM_Awal, p.KM_Akhir, p.Jumlah_KM, p.Foto_Odometer,
        p.ID_Kebun_Asal, p.ID_Kebun_Tujuan, p.Nama_Penumpang, p.Keterangan,
        d.Nama_Driver, k.No_Polisi, kb1.Nama_Kebun, kb2.Nama_Kebun,
        p.Status_Verifikasi
    """
    join = """
        FROM perjalanan p
        LEFT JOIN driver d ON p.ID_Driver = d.Id_Driver
        LEFT JOIN kendaraan k ON p.ID_Kendaraan = k.ID_Kendaraan
        LEFT JOIN kebun kb1 ON p.ID_Kebun_Asal = kb1.Id_Kebun
        LEFT JOIN kebun kb2 ON p.ID_Kebun_Tujuan = kb2.Id_Kebun
    """
    if session['role'] == 'kepala_operasional_gs':
        cur.execute(f"SELECT {kolom} {join} ORDER BY p.Tanggal DESC, p.Jam DESC")
    else:
        # Driver hanya lihat perjalanan miliknya
        cur.execute(f"""SELECT {kolom} {join}
            WHERE p.ID_Driver = (SELECT Id_Driver FROM driver WHERE Id_User = %s)
            ORDER BY p.Tanggal DESC, p.Jam DESC""", (session['user_id'],))

    data = cur.fetchall()
    cur.close()
    return render_template('perjalanan/list.html', data=data)


# =============================================
# TAMBAH PERJALANAN
# =============================================
@perjalanan_bp.route('/perjalanan/tambah', methods=['GET', 'POST'])
def tambah_perjalanan():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
        
    if session.get('role') == 'kepala_operasional_gs':
        flash('Akses ditolak. Hanya Driver yang bisa menambah data ini.', 'danger')
        return redirect(url_for('perjalanan.list_perjalanan'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()

    if request.method == 'POST':
        f = request.form

        # R2: validasi field wajib di sisi server (tidak hanya HTML5 'required').
        wajib = [('Tanggal', 'Tanggal'), ('Jam', 'Jam'), ('ID_Kendaraan', 'Kendaraan'),
                 ('KM_Akhir', 'KM Akhir'), ('ID_Kebun_Asal', 'Kebun Asal'),
                 ('ID_Kebun_Tujuan', 'Kebun Tujuan')]
        kurang = field_kosong(f, wajib)
        if kurang:
            cur.close()
            flash('Field wajib belum lengkap: ' + ', '.join(kurang) + '.', 'danger')
            return redirect(url_for('perjalanan.tambah_perjalanan'))

        id_kendaraan = f['ID_Kendaraan']

        # KM Awal otomatis & konsisten: tidak pernah di bawah KM terakhir
        # kendaraan (satu garis waktu KM lintas modul via get_last_km).
        # Nilai dari form (hasil isian otomatis) tetap dihormati, namun
        # diamankan dengan max() agar KM tidak mungkin mundur walau form
        # dimanipulasi atau JavaScript gagal memuat.
        km_terakhir = get_last_km(cur, id_kendaraan)
        km_awal  = max(float(f.get('KM_Awal', 0) or 0), km_terakhir)
        km_akhir = float(f.get('KM_Akhir', 0) or 0)

        # Validasi: KM Akhir tidak boleh lebih kecil dari KM Awal.
        if km_akhir < km_awal:
            cur.close()
            flash(f'KM Akhir ({km_akhir:.0f}) tidak boleh lebih kecil dari KM Awal '
                  f'({km_awal:.0f}). KM kendaraan tidak boleh mundur.', 'danger')
            return redirect(url_for('perjalanan.tambah_perjalanan'))

        foto_odometer = save_foto(request.files.get('Foto_Odometer'), 'odometer')
        jumlah_km = km_akhir - km_awal

        # Tentukan ID_Driver
        cur.execute("SELECT Id_Driver FROM driver WHERE Id_User = %s", (session['user_id'],))
        row = cur.fetchone()
        id_driver = row[0] if row else None

        cur.execute("""
            INSERT INTO perjalanan (
                Tanggal, Jam, ID_Driver, ID_Kendaraan,
                KM_Awal, KM_Akhir, Jumlah_KM, Foto_Odometer,
                ID_Kebun_Asal, ID_Kebun_Tujuan, Nama_Penumpang, Keterangan
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            f['Tanggal'], f['Jam'], id_driver, id_kendaraan,
            km_awal, km_akhir, jumlah_km, foto_odometer,
            f.get('ID_Kebun_Asal'), f.get('ID_Kebun_Tujuan'),
            f.get('Nama_Penumpang', ''), f.get('Keterangan', '')
        ))
        mysql.connection.commit()
        
        cur.execute("SELECT Nama_Driver FROM driver WHERE Id_Driver=%s", (id_driver,))
        nd = cur.fetchone()
        nama_driver = nd[0] if nd else "Unknown"
        
        cur.execute("SELECT No_Polisi FROM kendaraan WHERE ID_Kendaraan=%s", (id_kendaraan,))
        np = cur.fetchone()
        plat_nomor = np[0] if np else "Unknown"
        
        kirim_notifikasi_background('perjalanan', nama_driver, plat_nomor)
        cur.close()
        flash('Data perjalanan berhasil disimpan!', 'success')
        return redirect(url_for('perjalanan.list_perjalanan'))

    # Data untuk form
    cur.execute("SELECT ID_Kendaraan, No_Polisi, Merek, Tipe FROM kendaraan ORDER BY No_Polisi")
    kendaraans = cur.fetchall()
    cur.execute("SELECT Id_Kebun, Nama_Kebun FROM kebun ORDER BY Nama_Kebun")
    kebuns = cur.fetchall()

    # Kalau driver, ambil id_driver otomatis
    id_driver_login = None
    if session['role'] == 'driver':
        cur.execute("SELECT Id_Driver FROM driver WHERE Id_User = %s", (session['user_id'],))
        row = cur.fetchone()
        id_driver_login = row[0] if row else None

    cur.close()
    return render_template('perjalanan/tambah.html', kendaraans=kendaraans, kebuns=kebuns, id_driver_login=id_driver_login)


# =============================================
# EDIT PERJALANAN
# =============================================
@perjalanan_bp.route('/perjalanan/edit/<int:id>', methods=['GET', 'POST'])
def edit_perjalanan(id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()

    # Ambil data lama (sekaligus untuk validasi kepemilikan driver)
    cur.execute("SELECT * FROM perjalanan WHERE ID_Perjalanan=%s", (id,))
    lama = cur.fetchone()
    if not lama:
        cur.close()
        flash('Data perjalanan tidak ditemukan.', 'danger')
        return redirect(url_for('perjalanan.list_perjalanan'))

    # Hak edit terpusat: admin selalu boleh; driver hanya data MILIKNYA yang
    # masih 'Belum' diverifikasi. (lama[3]=ID_Driver, lama[13]=Status_Verifikasi)
    my_id_driver = None
    if session['role'] == 'driver':
        cur.execute("SELECT Id_Driver FROM driver WHERE Id_User = %s", (session['user_id'],))
        row = cur.fetchone()
        my_id_driver = row[0] if row else None
    if not boleh_edit(lama[13], lama[3], session['role'], my_id_driver):
        cur.close()
        if lama[13] == STATUS_TERVERIFIKASI:
            flash('Data sudah diverifikasi admin sehingga tidak dapat diubah.', 'warning')
        else:
            flash('Anda hanya dapat mengedit perjalanan milik Anda sendiri.', 'danger')
        return redirect(url_for('perjalanan.list_perjalanan'))

    if request.method == 'POST':
        f = request.form

        # R2: validasi field wajib di sisi server.
        wajib = [('Tanggal', 'Tanggal'), ('Jam', 'Jam'), ('ID_Kendaraan', 'Kendaraan'),
                 ('KM_Akhir', 'KM Akhir'), ('ID_Kebun_Asal', 'Kebun Asal'),
                 ('ID_Kebun_Tujuan', 'Kebun Tujuan')]
        if session['role'] == 'kepala_operasional_gs':
            wajib.append(('ID_Driver', 'Driver'))
        kurang = field_kosong(f, wajib)
        if kurang:
            cur.close()
            flash('Field wajib belum lengkap: ' + ', '.join(kurang) + '.', 'danger')
            return redirect(url_for('perjalanan.edit_perjalanan', id=id))

        foto_odometer = save_foto(request.files.get('Foto_Odometer'), 'odometer') or lama[8]  # kolom ke-9 = Foto_Odometer

        km_awal  = float(f.get('KM_Awal', 0) or 0)
        km_akhir = float(f.get('KM_Akhir', 0) or 0)
        jumlah_km = km_akhir - km_awal if km_akhir > km_awal else 0

        # ID_Driver: admin boleh mengganti, driver tetap miliknya
        if session['role'] == 'driver':
            id_driver = lama[3]
        else:
            id_driver = f.get('ID_Driver')

        cur.execute("""
            UPDATE perjalanan SET
                Tanggal=%s, Jam=%s, ID_Driver=%s, ID_Kendaraan=%s,
                KM_Awal=%s, KM_Akhir=%s, Jumlah_KM=%s, Foto_Odometer=%s,
                ID_Kebun_Asal=%s, ID_Kebun_Tujuan=%s, Nama_Penumpang=%s, Keterangan=%s
            WHERE ID_Perjalanan=%s
        """, (
            f['Tanggal'], f['Jam'], id_driver, f['ID_Kendaraan'],
            km_awal, km_akhir, jumlah_km, foto_odometer,
            f.get('ID_Kebun_Asal'), f.get('ID_Kebun_Tujuan'),
            f.get('Nama_Penumpang', ''), f.get('Keterangan', ''), id
        ))
        mysql.connection.commit()
        cur.close()
        flash('Data perjalanan berhasil diperbarui!', 'success')
        return redirect(url_for('perjalanan.list_perjalanan'))

    # Data untuk dropdown form
    cur.execute("SELECT Id_Driver, Nama_Driver FROM driver ORDER BY Nama_Driver")
    drivers = cur.fetchall()
    cur.execute("SELECT ID_Kendaraan, No_Polisi, Merek, Tipe FROM kendaraan ORDER BY No_Polisi")
    kendaraans = cur.fetchall()
    cur.execute("SELECT Id_Kebun, Nama_Kebun FROM kebun ORDER BY Nama_Kebun")
    kebuns = cur.fetchall()
    cur.close()
    return render_template('perjalanan/edit.html',
        p=lama, tanggal=str(lama[1]), jam=_fmt_time(lama[2]),
        drivers=drivers, kendaraans=kendaraans, kebuns=kebuns)


# =============================================
# HAPUS PERJALANAN
# =============================================
@perjalanan_bp.route('/perjalanan/hapus/<int:id>')
def hapus_perjalanan(id):
    if 'user_id' not in session or session['role'] != 'kepala_operasional_gs':
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('auth.login'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM perjalanan WHERE ID_Perjalanan=%s", (id,))
    mysql.connection.commit()
    cur.close()
    flash('Data perjalanan berhasil dihapus!', 'success')
    return redirect(url_for('perjalanan.list_perjalanan'))


# =============================================
# DETAIL PERJALANAN
# =============================================
@perjalanan_bp.route('/perjalanan/detail/<int:id>')
def detail_perjalanan(id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()
    # Kolom eksplisit: base(0-12), join(13-18) seperti semula, lalu status/audit
    # di indeks 19=Status, 20=Waktu_Verifikasi, 21=nama verifikator.
    cur.execute("""
        SELECT p.ID_Perjalanan, p.Tanggal, p.Jam, p.ID_Driver, p.ID_Kendaraan,
               p.KM_Awal, p.KM_Akhir, p.Jumlah_KM, p.Foto_Odometer,
               p.ID_Kebun_Asal, p.ID_Kebun_Tujuan, p.Nama_Penumpang, p.Keterangan,
               d.Nama_Driver, k.No_Polisi, k.Merek, k.Tipe,
               kb1.Nama_Kebun, kb2.Nama_Kebun,
               p.Status_Verifikasi, p.Waktu_Verifikasi, uv.Nama
        FROM perjalanan p
        LEFT JOIN driver d ON p.ID_Driver = d.Id_Driver
        LEFT JOIN kendaraan k ON p.ID_Kendaraan = k.ID_Kendaraan
        LEFT JOIN kebun kb1 ON p.ID_Kebun_Asal = kb1.Id_Kebun
        LEFT JOIN kebun kb2 ON p.ID_Kebun_Tujuan = kb2.Id_Kebun
        LEFT JOIN user uv ON p.Diverifikasi_Oleh = uv.Id_User
        WHERE p.ID_Perjalanan = %s
    """, (id,))
    perjalanan = cur.fetchone()

    if not perjalanan:
        cur.close()
        flash('Data perjalanan tidak ditemukan.', 'danger')
        return redirect(url_for('perjalanan.list_perjalanan'))

    # R1: driver hanya boleh melihat datanya sendiri (perjalanan[3]=ID_Driver).
    if session.get('role') == 'driver':
        cur.execute("SELECT Id_Driver FROM driver WHERE Id_User = %s", (session['user_id'],))
        r = cur.fetchone()
        if not r or perjalanan[3] != r[0]:
            cur.close()
            flash('Anda hanya dapat melihat data milik Anda sendiri.', 'danger')
            return redirect(url_for('perjalanan.list_perjalanan'))

    cur.close()
    return render_template('perjalanan/detail.html', p=perjalanan)


# =============================================
# VERIFIKASI / BATAL VERIFIKASI (ADMIN ONLY)
# =============================================
@perjalanan_bp.route('/perjalanan/verifikasi/<int:id>')
def verifikasi_perjalanan(id):
    if 'user_id' not in session or session['role'] != 'kepala_operasional_gs':
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('auth.login'))
    mysql = get_mysql()
    cur = mysql.connection.cursor()
    set_status_verifikasi(cur, 'perjalanan', 'ID_Perjalanan', id, True, session['user_id'])
    mysql.connection.commit()
    cur.close()
    flash('Data perjalanan berhasil diverifikasi.', 'success')
    return redirect(url_for('perjalanan.list_perjalanan'))


@perjalanan_bp.route('/perjalanan/batal-verifikasi/<int:id>')
def batal_verifikasi_perjalanan(id):
    if 'user_id' not in session or session['role'] != 'kepala_operasional_gs':
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('auth.login'))
    mysql = get_mysql()
    cur = mysql.connection.cursor()
    set_status_verifikasi(cur, 'perjalanan', 'ID_Perjalanan', id, False, session['user_id'])
    mysql.connection.commit()
    cur.close()
    flash('Verifikasi data perjalanan dibatalkan. Data dapat diedit kembali.', 'info')
    return redirect(url_for('perjalanan.list_perjalanan'))