from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
from models import get_last_km, boleh_edit, set_status_verifikasi, STATUS_TERVERIFIKASI, field_kosong
import os
from routes.email_helper import kirim_notifikasi_background

bbm_bp = Blueprint('bbm', __name__)
UPLOAD_FOLDER = 'static/uploads/bbm'
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
# LIST BBM
# =============================================
@bbm_bp.route('/bbm')
def list_bbm():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()

    # Kolom eksplisit (bukan b.*) agar indeks join stabil; Status di indeks 16.
    kolom = """
        b.Id_Pengisian, b.Tanggal, b.Jam, b.Id_Driver, b.Id_Kendaraan,
        b.Km_Awal, b.Km_Akhir, b.Jumlah_Km, b.Id_Kebun,
        b.Koordinat, b.Jenis_BBM, b.Jumlah_BBM, b.Foto_Nota,
        d.Nama_Driver, k.No_Polisi, kb.Nama_Kebun,
        b.Status_Verifikasi
    """
    join = """
        FROM pengisian_bbm b
        LEFT JOIN driver d ON b.Id_Driver = d.Id_Driver
        LEFT JOIN kendaraan k ON b.Id_Kendaraan = k.ID_Kendaraan
        LEFT JOIN kebun kb ON b.Id_Kebun = kb.Id_Kebun
    """
    if session['role'] == 'kepala_operasional_gs':
        cur.execute(f"SELECT {kolom} {join} ORDER BY b.Tanggal DESC, b.Jam DESC")
    else:
        cur.execute(f"""SELECT {kolom} {join}
            WHERE b.Id_Driver = (SELECT Id_Driver FROM driver WHERE Id_User = %s)
            ORDER BY b.Tanggal DESC, b.Jam DESC""", (session['user_id'],))

    data = cur.fetchall()
    cur.close()
    return render_template('bbm/list.html', data=data)


# =============================================
# TAMBAH BBM
# =============================================
@bbm_bp.route('/bbm/tambah', methods=['GET', 'POST'])
def tambah_bbm():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
        
    if session.get('role') == 'kepala_operasional_gs':
        flash('Akses ditolak. Hanya Driver yang bisa menambah data ini.', 'danger')
        return redirect(url_for('bbm.list_bbm'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()

    if request.method == 'POST':
        f = request.form

        # R2: validasi field wajib di sisi server.
        wajib = [('Tanggal', 'Tanggal'), ('Jam', 'Jam'), ('Id_Kendaraan', 'Kendaraan'),
                 ('Jenis_BBM', 'Jenis BBM'), ('Jumlah_BBM', 'Jumlah BBM'),
                 ('Km_Awal', 'KM Sebelum Pengisian'), ('Km_Akhir', 'KM Setelah Pengisian'),
                 ('Id_Kebun', 'Lokasi Pengisian'), ('Koordinat', 'Koordinat Lokasi')]
        kurang = field_kosong(f, wajib)
        if kurang:
            cur.close()
            flash('Field wajib belum lengkap: ' + ', '.join(kurang) + '.', 'danger')
            return redirect(url_for('bbm.tambah_bbm'))

        id_kendaraan = f['Id_Kendaraan']

        # KM Sebelum Pengisian otomatis & konsisten dengan garis waktu KM
        # lintas modul (get_last_km). max() menjaga agar tidak pernah mundur
        # walau isian otomatis gagal atau form dimanipulasi.
        km_terakhir = get_last_km(cur, id_kendaraan)
        km_awal  = max(float(f.get('Km_Awal', 0) or 0), km_terakhir)
        km_akhir = float(f.get('Km_Akhir', 0) or 0)

        # KM Setelah Pengisian wajib lebih besar dari KM Sebelum Pengisian
        if km_akhir < km_awal:
            cur.close()
            flash(f'KM Setelah Pengisian ({km_akhir:.0f}) tidak boleh lebih kecil dari '
                  f'KM Sebelum Pengisian ({km_awal:.0f}).', 'danger')
            return redirect(url_for('bbm.tambah_bbm'))
            
        if not request.files.get('Foto_Nota') or request.files.get('Foto_Nota').filename == '':
            cur.close()
            flash('Field wajib belum lengkap: Foto Nota / Struk.', 'danger')
            return redirect(url_for('bbm.tambah_bbm'))

                # Validasi Kapasitas Tangki BBM
        cur.execute("SELECT Kapasitas_TangkiBBM FROM kendaraan WHERE ID_Kendaraan=%s", (id_kendaraan,))
        k_tangki = cur.fetchone()
        jumlah_bbm_input = float(f['Jumlah_BBM'])
        
        if k_tangki and k_tangki[0]:
            max_tangki = float(k_tangki[0])
            if jumlah_bbm_input > max_tangki:
                cur.close()
                flash(f'Gagal: Jumlah pengisian BBM ({jumlah_bbm_input} L) melebihi kapasitas tangki kendaraan ({max_tangki} L).', 'danger')
                return redirect(url_for('bbm.tambah_bbm'))

        foto_nota = save_foto(request.files.get('Foto_Nota'), 'nota')
        jumlah_km = km_akhir - km_awal if km_akhir > km_awal else 0

        cur.execute("SELECT Id_Driver FROM driver WHERE Id_User = %s", (session['user_id'],))
        row = cur.fetchone()
        id_driver = row[0] if row else None

        cur.execute("""
            INSERT INTO pengisian_bbm (
                Tanggal, Jam, Id_Driver, Id_Kendaraan,
                Km_Awal, Km_Akhir, Jumlah_Km, Id_Kebun,
                Koordinat, Jenis_BBM, Jumlah_BBM, Foto_Nota
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            f['Tanggal'], f['Jam'], id_driver, id_kendaraan,
            km_awal, km_akhir, jumlah_km, f.get('Id_Kebun'),
            f.get('Koordinat', ''), f['Jenis_BBM'], f['Jumlah_BBM'], foto_nota
        ))
        mysql.connection.commit()
        
        cur.execute("SELECT Nama_Driver FROM driver WHERE Id_Driver=%s", (id_driver,))
        nd = cur.fetchone()
        nama_driver = nd[0] if nd else "Unknown"
        
        cur.execute("SELECT No_Polisi FROM kendaraan WHERE ID_Kendaraan=%s", (id_kendaraan,))
        np = cur.fetchone()
        plat_nomor = np[0] if np else "Unknown"
        
        kirim_notifikasi_background('BBM', nama_driver, plat_nomor)
        cur.close()
        flash('Data pengisian BBM berhasil disimpan!', 'success')
        return redirect(url_for('bbm.list_bbm'))

    cur.execute("SELECT ID_Kendaraan, No_Polisi, Merek, Tipe, Jenis_BBM1, Jenis_BBM2, Jenis_BBM3, Kapasitas_TangkiBBM FROM kendaraan ORDER BY No_Polisi")
    kendaraans = cur.fetchall()
    cur.execute("SELECT Id_Kebun, Nama_Kebun FROM kebun ORDER BY Nama_Kebun")
    kebuns = cur.fetchall()

    id_driver_login = None
    if session['role'] == 'driver':
        cur.execute("SELECT Id_Driver FROM driver WHERE Id_User = %s", (session['user_id'],))
        row = cur.fetchone()
        id_driver_login = row[0] if row else None

    cur.close()
    return render_template('bbm/tambah.html', kendaraans=kendaraans, kebuns=kebuns, id_driver_login=id_driver_login)


# =============================================
# EDIT BBM
# =============================================
@bbm_bp.route('/bbm/edit/<int:id>', methods=['GET', 'POST'])
def edit_bbm(id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()

    cur.execute("SELECT * FROM pengisian_bbm WHERE Id_Pengisian=%s", (id,))
    lama = cur.fetchone()
    if not lama:
        cur.close()
        flash('Data pengisian BBM tidak ditemukan.', 'danger')
        return redirect(url_for('bbm.list_bbm'))

    # Hak edit terpusat: admin selalu boleh; driver hanya data MILIKNYA yang
    # masih 'Belum' diverifikasi. (lama[3]=Id_Driver, lama[13]=Status_Verifikasi)
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
            flash('Anda hanya dapat mengedit data BBM milik Anda sendiri.', 'danger')
        return redirect(url_for('bbm.list_bbm'))

    if request.method == 'POST':
        f = request.form

        # R2: validasi field wajib di sisi server.
        wajib = [('Tanggal', 'Tanggal'), ('Jam', 'Jam'), ('Id_Kendaraan', 'Kendaraan'),
                 ('Jenis_BBM', 'Jenis BBM'), ('Jumlah_BBM', 'Jumlah BBM'),
                 ('Km_Awal', 'KM Sebelum Pengisian'), ('Km_Akhir', 'KM Setelah Pengisian'),
                 ('Id_Kebun', 'Lokasi Pengisian'), ('Koordinat', 'Koordinat Lokasi')]
        if session['role'] == 'kepala_operasional_gs':
            wajib.append(('Id_Driver', 'Driver'))
        kurang = field_kosong(f, wajib)
        if kurang:
            cur.close()
            flash('Field wajib belum lengkap: ' + ', '.join(kurang) + '.', 'danger')
            return redirect(url_for('bbm.edit_bbm', id=id))

                # Validasi Kapasitas Tangki BBM
        cur.execute("SELECT Kapasitas_TangkiBBM FROM kendaraan WHERE ID_Kendaraan=%s", (f['Id_Kendaraan'],))
        k_tangki = cur.fetchone()
        jumlah_bbm_input = float(f['Jumlah_BBM'])
        
        if k_tangki and k_tangki[0]:
            max_tangki = float(k_tangki[0])
            if jumlah_bbm_input > max_tangki:
                cur.close()
                flash(f'Gagal: Jumlah pengisian BBM ({jumlah_bbm_input} L) melebihi kapasitas tangki kendaraan ({max_tangki} L).', 'danger')
                return redirect(url_for('bbm.edit_bbm', id=id))
        
        foto_nota = save_foto(request.files.get('Foto_Nota'), 'nota') or lama[12]  # kolom ke-13 = Foto_Nota

        km_awal  = float(f.get('Km_Awal', 0) or 0)
        km_akhir = float(f.get('Km_Akhir', 0) or 0)
        
        if km_akhir < km_awal:
            cur.close()
            flash(f'KM Setelah Pengisian ({km_akhir:.0f}) tidak boleh lebih kecil dari '
                  f'KM Sebelum Pengisian ({km_awal:.0f}).', 'danger')
            return redirect(url_for('bbm.edit_bbm', id=id))
            
        jumlah_km = km_akhir - km_awal

        if session['role'] == 'driver':
            id_driver = lama[3]
        else:
            id_driver = f.get('Id_Driver')

        cur.execute("""
            UPDATE pengisian_bbm SET
                Tanggal=%s, Jam=%s, Id_Driver=%s, Id_Kendaraan=%s,
                Km_Awal=%s, Km_Akhir=%s, Jumlah_Km=%s, Id_Kebun=%s,
                Koordinat=%s, Jenis_BBM=%s, Jumlah_BBM=%s, Foto_Nota=%s
            WHERE Id_Pengisian=%s
        """, (
            f['Tanggal'], f['Jam'], id_driver, f['Id_Kendaraan'],
            km_awal, km_akhir, jumlah_km, f.get('Id_Kebun'),
            f.get('Koordinat', ''), f['Jenis_BBM'], f['Jumlah_BBM'], foto_nota, id
        ))
        mysql.connection.commit()
        cur.close()
        flash('Data pengisian BBM berhasil diperbarui!', 'success')
        return redirect(url_for('bbm.list_bbm'))

    cur.execute("SELECT Id_Driver, Nama_Driver FROM driver ORDER BY Nama_Driver")
    drivers = cur.fetchall()
    cur.execute("SELECT ID_Kendaraan, No_Polisi, Merek, Tipe, Jenis_BBM1, Jenis_BBM2, Jenis_BBM3, Kapasitas_TangkiBBM FROM kendaraan ORDER BY No_Polisi")
    kendaraans = cur.fetchall()
    cur.execute("SELECT Id_Kebun, Nama_Kebun FROM kebun ORDER BY Nama_Kebun")
    kebuns = cur.fetchall()
    cur.close()
    return render_template('bbm/edit.html',
        b=lama, tanggal=str(lama[1]), jam=_fmt_time(lama[2]),
        drivers=drivers, kendaraans=kendaraans, kebuns=kebuns)


# =============================================
# DETAIL BBM
# =============================================
@bbm_bp.route('/bbm/detail/<int:id>')
def detail_bbm(id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()
    # Kolom eksplisit: base(0-12), join(13-17), lalu
    # 18=Status, 19=Waktu_Verifikasi, 20=nama verifikator.
    cur.execute("""
        SELECT b.Id_Pengisian, b.Tanggal, b.Jam, b.Id_Driver, b.Id_Kendaraan,
               b.Km_Awal, b.Km_Akhir, b.Jumlah_Km, b.Id_Kebun,
               b.Koordinat, b.Jenis_BBM, b.Jumlah_BBM, b.Foto_Nota,
               d.Nama_Driver, k.No_Polisi, k.Merek, k.Tipe, kb.Nama_Kebun,
               b.Status_Verifikasi, b.Waktu_Verifikasi, uv.Nama
        FROM pengisian_bbm b
        LEFT JOIN driver d ON b.Id_Driver = d.Id_Driver
        LEFT JOIN kendaraan k ON b.Id_Kendaraan = k.ID_Kendaraan
        LEFT JOIN kebun kb ON b.Id_Kebun = kb.Id_Kebun
        LEFT JOIN user uv ON b.Diverifikasi_Oleh = uv.Id_User
        WHERE b.Id_Pengisian = %s
    """, (id,))
    bbm = cur.fetchone()

    if not bbm:
        cur.close()
        flash('Data pengisian BBM tidak ditemukan.', 'danger')
        return redirect(url_for('bbm.list_bbm'))

    # R1: driver hanya boleh melihat datanya sendiri (bbm[3]=Id_Driver).
    if session.get('role') == 'driver':
        cur.execute("SELECT Id_Driver FROM driver WHERE Id_User = %s", (session['user_id'],))
        r = cur.fetchone()
        if not r or bbm[3] != r[0]:
            cur.close()
            flash('Anda hanya dapat melihat data milik Anda sendiri.', 'danger')
            return redirect(url_for('bbm.list_bbm'))

    cur.close()
    return render_template('bbm/detail.html', b=bbm)


# =============================================
# HAPUS BBM
# =============================================
@bbm_bp.route('/bbm/hapus/<int:id>')
def hapus_bbm(id):
    if 'user_id' not in session or session['role'] != 'kepala_operasional_gs':
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('auth.login'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM pengisian_bbm WHERE Id_Pengisian=%s", (id,))
    mysql.connection.commit()
    cur.close()
    flash('Data BBM berhasil dihapus!', 'success')
    return redirect(url_for('bbm.list_bbm'))


# =============================================
# VERIFIKASI / BATAL VERIFIKASI (ADMIN ONLY)
# =============================================
@bbm_bp.route('/bbm/verifikasi/<int:id>')
def verifikasi_bbm(id):
    if 'user_id' not in session or session['role'] != 'kepala_operasional_gs':
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('auth.login'))
    mysql = get_mysql()
    cur = mysql.connection.cursor()
    set_status_verifikasi(cur, 'pengisian_bbm', 'Id_Pengisian', id, True, session['user_id'])
    mysql.connection.commit()
    cur.close()
    flash('Data pengisian BBM berhasil diverifikasi.', 'success')
    return redirect(url_for('bbm.list_bbm'))


@bbm_bp.route('/bbm/batal-verifikasi/<int:id>')
def batal_verifikasi_bbm(id):
    if 'user_id' not in session or session['role'] != 'kepala_operasional_gs':
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('auth.login'))
    mysql = get_mysql()
    cur = mysql.connection.cursor()
    set_status_verifikasi(cur, 'pengisian_bbm', 'Id_Pengisian', id, False, session['user_id'])
    mysql.connection.commit()
    cur.close()
    flash('Verifikasi data BBM dibatalkan. Data dapat diedit kembali.', 'info')
    return redirect(url_for('bbm.list_bbm'))