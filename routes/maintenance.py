from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
from models import get_last_km, boleh_edit, set_status_verifikasi, STATUS_TERVERIFIKASI, field_kosong
import os
from routes.email_helper import kirim_notifikasi_background

maintenance_bp = Blueprint('maintenance', __name__)
UPLOAD_FOLDER = 'static/uploads/maintenance'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

def allowed_file(f):
    return '.' in f and f.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_mysql():
    from app import mysql
    return mysql

def save_foto(file, prefix):
    if file and file.filename != '' and allowed_file(file.filename):
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        filename = secure_filename(f"{prefix}_{file.filename}")
        file.save(os.path.join(UPLOAD_FOLDER, filename))
        return filename
    return None


# =============================================
# LIST MAINTENANCE
# =============================================
@maintenance_bp.route('/maintenance')
def list_maintenance():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()

    # Kolom eksplisit (bukan m.*) agar indeks join stabil; Status di indeks 15.
    kolom = """
        m.ID_Maintenance, m.ID_Kendaraan, m.ID_Driver, m.Tanggal, m.KM_Kendaraan,
        m.Lokasi_Maintenance, m.Koordinat, m.Keluhan, m.Jumlah_Keluhan,
        m.Spareparts, m.Jumlah_Spareparts, m.Foto_Perbaikan, m.Foto_Nota_SpareParts,
        d.Nama_Driver, k.No_Polisi,
        m.Status_Verifikasi
    """
    join = """
        FROM maintenance m
        LEFT JOIN driver d ON m.ID_Driver = d.Id_Driver
        LEFT JOIN kendaraan k ON m.ID_Kendaraan = k.ID_Kendaraan
    """
    if session['role'] == 'kepala_operasional_gs':
        cur.execute(f"SELECT {kolom} {join} ORDER BY m.Tanggal DESC")
    else:
        cur.execute(f"""SELECT {kolom} {join}
            WHERE m.ID_Driver = (SELECT Id_Driver FROM driver WHERE Id_User = %s)
            ORDER BY m.Tanggal DESC""", (session['user_id'],))

    data = cur.fetchall()
    cur.close()
    return render_template('maintenance/list.html', data=data)


# =============================================
# TAMBAH MAINTENANCE
# =============================================
@maintenance_bp.route('/maintenance/tambah', methods=['GET', 'POST'])
def tambah_maintenance():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
        
    if session.get('role') == 'kepala_operasional_gs':
        flash('Akses ditolak. Hanya Driver yang bisa menambah data ini.', 'danger')
        return redirect(url_for('maintenance.list_maintenance'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()

    if request.method == 'POST':
        f = request.form

        # R2: validasi field wajib di sisi server.
        kurang = field_kosong(f, [('Tanggal', 'Tanggal'), ('ID_Kendaraan', 'Kendaraan'),
                                  ('Lokasi_Maintenance', 'Lokasi Maintenance'), ('Koordinat', 'Koordinat Lokasi'),
                                  ('Keluhan', 'Daftar Keluhan'), ('Spareparts', 'Daftar Sparepart Diganti')])
        if 'Foto_Perbaikan' not in request.files or request.files['Foto_Perbaikan'].filename == '':
            kurang.append('Foto Perbaikan')
        if 'Foto_Nota_SpareParts' not in request.files or request.files['Foto_Nota_SpareParts'].filename == '':
            kurang.append('Foto Nota Sparepart')
            
        if kurang:
            cur.close()
            flash('Field wajib belum lengkap: ' + ', '.join(kurang) + '.', 'danger')
            return redirect(url_for('maintenance.tambah_maintenance'))

        id_kendaraan = f['ID_Kendaraan']

        # Maintenance adalah peristiwa titik-waktu (kendaraan masuk bengkel),
        # bukan perjalanan, sehingga cukup SATU pembacaan odometer: KM_Kendaraan.
        # Nilainya konsisten dengan garis waktu KM lintas modul (get_last_km),
        # dan max() menjaga agar tidak pernah mundur walau isian otomatis gagal.
        km_terakhir = get_last_km(cur, id_kendaraan)
        km_kendaraan = int(max(float(f.get('KM_Kendaraan', 0) or 0), km_terakhir))

        foto_perbaikan  = save_foto(request.files.get('Foto_Perbaikan'),       'perbaikan')
        foto_nota       = save_foto(request.files.get('Foto_Nota_SpareParts'), 'nota_spare')

        cur.execute("SELECT Id_Driver FROM driver WHERE Id_User = %s", (session['user_id'],))
        row = cur.fetchone()
        id_driver = row[0] if row else None

        # Hitung jumlah keluhan & spareparts dari textarea
        keluhan   = f.get('Keluhan', '')
        sparepart = f.get('Spareparts', '')
        jml_keluhan   = len([k for k in keluhan.split('\n') if k.strip()]) if keluhan else 0
        jml_sparepart = len([s for s in sparepart.split('\n') if s.strip()]) if sparepart else 0

        cur.execute("""
            INSERT INTO maintenance (
                ID_Kendaraan, ID_Driver, Tanggal, KM_Kendaraan,
                Lokasi_Maintenance, Koordinat,
                Keluhan, Jumlah_Keluhan,
                Spareparts, Jumlah_Spareparts,
                Foto_Perbaikan, Foto_Nota_SpareParts
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            id_kendaraan, id_driver, f['Tanggal'], km_kendaraan,
            f.get('Lokasi_Maintenance', ''), f.get('Koordinat', ''),
            keluhan, jml_keluhan,
            sparepart, jml_sparepart,
            foto_perbaikan, foto_nota
        ))
        mysql.connection.commit()
        
        cur.execute("SELECT Nama_Driver FROM driver WHERE Id_Driver=%s", (id_driver,))
        nd = cur.fetchone()
        nama_driver = nd[0] if nd else "Unknown"
        
        cur.execute("SELECT No_Polisi FROM kendaraan WHERE ID_Kendaraan=%s", (id_kendaraan,))
        np = cur.fetchone()
        plat_nomor = np[0] if np else "Unknown"
        
        kirim_notifikasi_background('maintenance', nama_driver, plat_nomor)
        cur.close()
        flash('Data maintenance berhasil disimpan!', 'success')
        return redirect(url_for('maintenance.list_maintenance'))

    cur.execute("SELECT ID_Kendaraan, No_Polisi, Merek, Tipe FROM kendaraan ORDER BY No_Polisi")
    kendaraans = cur.fetchall()

    id_driver_login = None
    if session['role'] == 'driver':
        cur.execute("SELECT Id_Driver FROM driver WHERE Id_User = %s", (session['user_id'],))
        row = cur.fetchone()
        id_driver_login = row[0] if row else None

    cur.close()
    return render_template('maintenance/tambah.html', kendaraans=kendaraans, id_driver_login=id_driver_login)


# =============================================
# DETAIL MAINTENANCE
# =============================================
@maintenance_bp.route('/maintenance/detail/<int:id>')
def detail_maintenance(id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()
    # Kolom eksplisit: base(0-12), join(13-14) seperti semula, lalu
    # 15=Status, 16=Waktu_Verifikasi, 17=nama verifikator.
    cur.execute("""
        SELECT m.ID_Maintenance, m.ID_Kendaraan, m.ID_Driver, m.Tanggal, m.KM_Kendaraan,
               m.Lokasi_Maintenance, m.Koordinat, m.Keluhan, m.Jumlah_Keluhan,
               m.Spareparts, m.Jumlah_Spareparts, m.Foto_Perbaikan, m.Foto_Nota_SpareParts,
               d.Nama_Driver, k.No_Polisi,
               m.Status_Verifikasi, m.Waktu_Verifikasi, uv.Nama
        FROM maintenance m
        LEFT JOIN driver d ON m.ID_Driver = d.Id_Driver
        LEFT JOIN kendaraan k ON m.ID_Kendaraan = k.ID_Kendaraan
        LEFT JOIN user uv ON m.Diverifikasi_Oleh = uv.Id_User
        WHERE m.ID_Maintenance = %s
    """, (id,))
    maint = cur.fetchone()

    if not maint:
        cur.close()
        flash('Data maintenance tidak ditemukan.', 'danger')
        return redirect(url_for('maintenance.list_maintenance'))

    # R1: driver hanya boleh melihat datanya sendiri (maint[2]=ID_Driver).
    if session.get('role') == 'driver':
        cur.execute("SELECT Id_Driver FROM driver WHERE Id_User = %s", (session['user_id'],))
        r = cur.fetchone()
        if not r or maint[2] != r[0]:
            cur.close()
            flash('Anda hanya dapat melihat data milik Anda sendiri.', 'danger')
            return redirect(url_for('maintenance.list_maintenance'))

    cur.close()
    return render_template('maintenance/detail.html', maint=maint)


# =============================================
# EDIT MAINTENANCE
# =============================================
@maintenance_bp.route('/maintenance/edit/<int:id>', methods=['GET', 'POST'])
def edit_maintenance(id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()

    cur.execute("SELECT * FROM maintenance WHERE ID_Maintenance=%s", (id,))
    lama = cur.fetchone()
    if not lama:
        cur.close()
        flash('Data maintenance tidak ditemukan.', 'danger')
        return redirect(url_for('maintenance.list_maintenance'))

    # Hak edit terpusat: admin selalu boleh; driver hanya data MILIKNYA yang
    # masih 'Belum'. (lama[2]=ID_Driver, lama[13]=Status_Verifikasi)
    my_id_driver = None
    if session['role'] == 'driver':
        cur.execute("SELECT Id_Driver FROM driver WHERE Id_User = %s", (session['user_id'],))
        row = cur.fetchone()
        my_id_driver = row[0] if row else None
    if not boleh_edit(lama[13], lama[2], session['role'], my_id_driver):
        cur.close()
        if lama[13] == STATUS_TERVERIFIKASI:
            flash('Data sudah diverifikasi admin sehingga tidak dapat diubah.', 'warning')
        else:
            flash('Anda hanya dapat mengedit maintenance milik Anda sendiri.', 'danger')
        return redirect(url_for('maintenance.list_maintenance'))

    if request.method == 'POST':
        f = request.form

        # R2: validasi field wajib di sisi server.
        kurang = field_kosong(f, [('Tanggal', 'Tanggal'), ('ID_Kendaraan', 'Kendaraan'),
                                  ('Lokasi_Maintenance', 'Lokasi Maintenance'), ('Koordinat', 'Koordinat Lokasi'),
                                  ('Keluhan', 'Daftar Keluhan'), ('Spareparts', 'Daftar Sparepart Diganti')])
        
        if ('Foto_Perbaikan' not in request.files or request.files['Foto_Perbaikan'].filename == '') and not lama[11]:
            kurang.append('Foto Perbaikan')
        if ('Foto_Nota_SpareParts' not in request.files or request.files['Foto_Nota_SpareParts'].filename == '') and not lama[12]:
            kurang.append('Foto Nota Sparepart')

        if kurang:
            cur.close()
            flash('Field wajib belum lengkap: ' + ', '.join(kurang) + '.', 'danger')
            return redirect(url_for('maintenance.edit_maintenance', id=id))

        id_kendaraan = f['ID_Kendaraan']

        # KM tetap konsisten dengan garis waktu KM lintas modul.
        km_terakhir = get_last_km(cur, id_kendaraan)
        km_kendaraan = int(max(float(f.get('KM_Kendaraan', 0) or 0), km_terakhir))

        foto_perbaikan = save_foto(request.files.get('Foto_Perbaikan'),       'perbaikan')   or lama[11]
        foto_nota      = save_foto(request.files.get('Foto_Nota_SpareParts'), 'nota_spare')  or lama[12]

        # Driver tetap pemilik; admin boleh mengganti driver.
        if session['role'] == 'driver':
            id_driver = lama[2]
        else:
            id_driver = f.get('ID_Driver') or lama[2]

        keluhan   = f.get('Keluhan', '')
        sparepart = f.get('Spareparts', '')
        jml_keluhan   = len([k for k in keluhan.split('\n') if k.strip()]) if keluhan else 0
        jml_sparepart = len([s for s in sparepart.split('\n') if s.strip()]) if sparepart else 0

        cur.execute("""
            UPDATE maintenance SET
                ID_Kendaraan=%s, ID_Driver=%s, Tanggal=%s, KM_Kendaraan=%s,
                Lokasi_Maintenance=%s, Koordinat=%s,
                Keluhan=%s, Jumlah_Keluhan=%s, Spareparts=%s, Jumlah_Spareparts=%s,
                Foto_Perbaikan=%s, Foto_Nota_SpareParts=%s
            WHERE ID_Maintenance=%s
        """, (
            id_kendaraan, id_driver, f['Tanggal'], km_kendaraan,
            f.get('Lokasi_Maintenance', ''), f.get('Koordinat', ''),
            keluhan, jml_keluhan, sparepart, jml_sparepart,
            foto_perbaikan, foto_nota, id
        ))
        mysql.connection.commit()
        cur.close()
        flash('Data maintenance berhasil diperbarui!', 'success')
        return redirect(url_for('maintenance.list_maintenance'))

    cur.execute("SELECT Id_Driver, Nama_Driver FROM driver ORDER BY Nama_Driver")
    drivers = cur.fetchall()
    cur.execute("SELECT ID_Kendaraan, No_Polisi, Merek, Tipe FROM kendaraan ORDER BY No_Polisi")
    kendaraans = cur.fetchall()
    cur.close()
    return render_template('maintenance/edit.html', m=lama, drivers=drivers, kendaraans=kendaraans)


# =============================================
# HAPUS MAINTENANCE
# =============================================
@maintenance_bp.route('/maintenance/hapus/<int:id>')
def hapus_maintenance(id):
    if 'user_id' not in session or session['role'] != 'kepala_operasional_gs':
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('auth.login'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM maintenance WHERE ID_Maintenance=%s", (id,))
    mysql.connection.commit()
    cur.close()
    flash('Data maintenance berhasil dihapus!', 'success')
    return redirect(url_for('maintenance.list_maintenance'))


# =============================================
# VERIFIKASI / BATAL VERIFIKASI (ADMIN ONLY)
# =============================================
@maintenance_bp.route('/maintenance/verifikasi/<int:id>')
def verifikasi_maintenance(id):
    if 'user_id' not in session or session['role'] != 'kepala_operasional_gs':
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('auth.login'))
    mysql = get_mysql()
    cur = mysql.connection.cursor()
    set_status_verifikasi(cur, 'maintenance', 'ID_Maintenance', id, True, session['user_id'])
    mysql.connection.commit()
    cur.close()
    flash('Data maintenance berhasil diverifikasi.', 'success')
    return redirect(url_for('maintenance.list_maintenance'))


@maintenance_bp.route('/maintenance/batal-verifikasi/<int:id>')
def batal_verifikasi_maintenance(id):
    if 'user_id' not in session or session['role'] != 'kepala_operasional_gs':
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('auth.login'))
    mysql = get_mysql()
    cur = mysql.connection.cursor()
    set_status_verifikasi(cur, 'maintenance', 'ID_Maintenance', id, False, session['user_id'])
    mysql.connection.commit()
    cur.close()
    flash('Verifikasi data maintenance dibatalkan. Data dapat diedit kembali.', 'info')
    return redirect(url_for('maintenance.list_maintenance'))