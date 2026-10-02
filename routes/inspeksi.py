from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
from models import get_last_km, boleh_edit, set_status_verifikasi, STATUS_TERVERIFIKASI, field_kosong
import os
from datetime import datetime
from routes.email_helper import kirim_notifikasi_background

inspeksi_bp = Blueprint('inspeksi', __name__)
UPLOAD_FOLDER = 'static/uploads/inspeksi'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

# 17 komponen kondisi inspeksi (nilai sah: 'Normal' / 'Tidak Normal').
KOMPONEN_INSPEKSI = [
    'Oli_Mesin', 'Oli_Transmisi_Gardan', 'Air_Radiator', 'Minyak_Rem', 'V_Belt',
    'Body_Exterior', 'Ban', 'Interior_Kelengkapan', 'Lampu_Lampu', 'Suara_Mesin',
    'Getaran_Mesin', 'Indikator_Dashboard', 'Asap_Knalpot', 'Transmisi',
    'Power_Steering', 'Pengereman', 'Suspensi_Kaki_Kaki',
]

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
# LIST INSPEKSI
# =============================================
@inspeksi_bp.route('/inspeksi')
def list_inspeksi():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()

    # Kolom status & pemilik ditambahkan di akhir (indeks 7=ID_Driver, 8=Status)
    # agar indeks lama (0-6) tetap stabil di template.
    kolom = """
        i.ID_Inspeksi, i.Tanggal, i.KM_Kendaraan, i.Koordinat,
        d.Nama_Driver, k.No_Polisi,
        i.ID_Driver, i.Status_Verifikasi
    """
    join = """
        FROM inspeksi i
        LEFT JOIN driver d ON i.ID_Driver = d.Id_Driver
        LEFT JOIN kendaraan k ON i.ID_Kendaraan = k.ID_Kendaraan
    """
    if session['role'] == 'kepala_operasional_gs':
        cur.execute(f"SELECT {kolom} {join} ORDER BY i.Tanggal DESC")
    else:
        cur.execute(f"""SELECT {kolom} {join}
            WHERE i.ID_Driver = (SELECT Id_Driver FROM driver WHERE Id_User = %s)
            ORDER BY i.Tanggal DESC""", (session['user_id'],))

    data = cur.fetchall()
    cur.close()
    return render_template('inspeksi/list.html', data=data)


# =============================================
# TAMBAH INSPEKSI
# =============================================
@inspeksi_bp.route('/inspeksi/tambah', methods=['GET', 'POST'])
def tambah_inspeksi():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
        
    if session.get('role') == 'kepala_operasional_gs':
        flash('Akses ditolak. Hanya Driver yang bisa menambah data ini.', 'danger')
        return redirect(url_for('inspeksi.list_inspeksi'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()

    if request.method == 'POST':
        f = request.form

        # R2: validasi field wajib + 17 kondisi komponen di sisi server.
        masalah = field_kosong(f, [('Tanggal', 'Tanggal'), ('ID_Kendaraan', 'Kendaraan'), ('Koordinat', 'Koordinat Lokasi')])
        
        for k in KOMPONEN_INSPEKSI:
            kondisi = f.get(k)
            if kondisi not in ('Normal', 'Tidak Normal'):
                if 'Kondisi 17 komponen' not in masalah:
                    masalah.append('Kondisi 17 komponen')
            elif kondisi == 'Tidak Normal':
                # Cek keterangan
                ket = f.get(f'Keterangan_{k}')
                if not ket or ket.strip() == '':
                    masalah.append(f'Catatan Kondisi untuk {k.replace("_", " ")}')
                # Cek foto (jika komponen ini membutuhkan foto)
                foto_field = f'Foto_{k}'
                if foto_field in request.files:
                    # Ini berarti komponen ini memang mendukung upload foto di HTML
                    file = request.files.get(foto_field)
                    if not file or file.filename == '':
                        masalah.append(f'Foto Bukti untuk {k.replace("_", " ")}')

        if masalah:
            cur.close()
            flash('Data wajib belum lengkap: ' + ', '.join(masalah) + '.', 'danger')
            return redirect(url_for('inspeksi.tambah_inspeksi'))

        id_kendaraan = f['ID_Kendaraan']

        # Inspeksi = peristiwa titik-waktu (pemeriksaan kendaraan), sama sifatnya
        # dengan maintenance: cukup SATU pembacaan odometer (KM_Kendaraan) yang
        # konsisten dengan garis waktu KM lintas modul via get_last_km. max()
        # menjaga agar tidak pernah mundur walau isian otomatis gagal/dikosongkan.
        km_terakhir = get_last_km(cur, id_kendaraan)
        km_kendaraan = int(max(float(f.get('KM_Kendaraan', 0) or 0), km_terakhir))

        # Simpan semua foto
        fotos = {
            'Foto_Oli_Mesin'              : save_foto(request.files.get('Foto_Oli_Mesin'),               'oli_mesin'),
            'Foto_Oli_Transmisi_Gardan'   : save_foto(request.files.get('Foto_Oli_Transmisi_Gardan'),    'oli_transmisi'),
            'Foto_Air_Radiator'           : save_foto(request.files.get('Foto_Air_Radiator'),            'air_radiator'),
            'Foto_Minyak_Rem'             : save_foto(request.files.get('Foto_Minyak_Rem'),              'minyak_rem'),
            'Foto_V_Belt'                 : save_foto(request.files.get('Foto_V_Belt'),                  'v_belt'),
            'Foto_Body_Exterior'          : save_foto(request.files.get('Foto_Body_Exterior'),           'body_exterior'),
            'Foto_Ban'                    : save_foto(request.files.get('Foto_Ban'),                     'ban'),
            'Foto_Interior_Kelengkapan'   : save_foto(request.files.get('Foto_Interior_Kelengkapan'),    'interior'),
            'Foto_Indikator_Dashboard'    : save_foto(request.files.get('Foto_Indikator_Dashboard'),     'dashboard'),
            'Foto_Asap_Knalpot'           : save_foto(request.files.get('Foto_Asap_Knalpot'),           'knalpot'),
        }

        if session['role'] == 'driver':
            cur.execute("SELECT Id_Driver FROM driver WHERE Id_User = %s", (session['user_id'],))
            row = cur.fetchone()
            id_driver = row[0] if row else None
        else:
            id_driver = f.get('ID_Driver')

        cur.execute("""
            INSERT INTO inspeksi (
                ID_Driver, ID_Kendaraan, Tanggal, KM_Kendaraan, Koordinat,
                Oli_Mesin, Keterangan_Oli_Mesin, Foto_Oli_Mesin,
                Oli_Transmisi_Gardan, Keterangan_Oli_Transmisi_Gardan, Foto_Oli_Transmisi_Gardan,
                Air_Radiator, Keterangan_Air_Radiator, Foto_Air_Radiator,
                Minyak_Rem, Keterangan_Minyak_Rem, Foto_Minyak_Rem,
                V_Belt, Keterangan_V_Belt, Foto_V_Belt,
                Body_Exterior, Keterangan_Body_Exterior, Foto_Body_Exterior,
                Ban, Keterangan_Ban, Foto_Ban,
                Interior_Kelengkapan, Keterangan_Interior_Kelengkapan, Foto_Interior_Kelengkapan,
                Lampu_Lampu, Keterangan_Lampu_Lampu,
                Suara_Mesin, Keterangan_Suara_Mesin,
                Getaran_Mesin, Keterangan_Getaran_Mesin,
                Indikator_Dashboard, Keterangan_Indikator_Dashboard, Foto_Indikator_Dashboard,
                Asap_Knalpot, Keterangan_Asap_Knalpot, Foto_Asap_Knalpot,
                Transmisi, Keterangan_Transmisi,
                Power_Steering, Keterangan_Power_Steering,
                Pengereman, Keterangan_Pengereman,
                Suspensi_Kaki_Kaki, Keterangan_Suspensi_Kaki_Kaki,
                Catatan
            ) VALUES (
                %s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
            )
        """, (
            id_driver, id_kendaraan, f['Tanggal'],
            km_kendaraan, f.get('Koordinat', ''),
            f.get('Oli_Mesin'), f.get('Keterangan_Oli_Mesin',''), fotos['Foto_Oli_Mesin'],
            f.get('Oli_Transmisi_Gardan'), f.get('Keterangan_Oli_Transmisi_Gardan',''), fotos['Foto_Oli_Transmisi_Gardan'],
            f.get('Air_Radiator'), f.get('Keterangan_Air_Radiator',''), fotos['Foto_Air_Radiator'],
            f.get('Minyak_Rem'), f.get('Keterangan_Minyak_Rem',''), fotos['Foto_Minyak_Rem'],
            f.get('V_Belt'), f.get('Keterangan_V_Belt',''), fotos['Foto_V_Belt'],
            f.get('Body_Exterior'), f.get('Keterangan_Body_Exterior',''), fotos['Foto_Body_Exterior'],
            f.get('Ban'), f.get('Keterangan_Ban',''), fotos['Foto_Ban'],
            f.get('Interior_Kelengkapan'), f.get('Keterangan_Interior_Kelengkapan',''), fotos['Foto_Interior_Kelengkapan'],
            f.get('Lampu_Lampu'), f.get('Keterangan_Lampu_Lampu',''),
            f.get('Suara_Mesin'), f.get('Keterangan_Suara_Mesin',''),
            f.get('Getaran_Mesin'), f.get('Keterangan_Getaran_Mesin',''),
            f.get('Indikator_Dashboard'), f.get('Keterangan_Indikator_Dashboard',''), fotos['Foto_Indikator_Dashboard'],
            f.get('Asap_Knalpot'), f.get('Keterangan_Asap_Knalpot',''), fotos['Foto_Asap_Knalpot'],
            f.get('Transmisi'), f.get('Keterangan_Transmisi',''),
            f.get('Power_Steering'), f.get('Keterangan_Power_Steering',''),
            f.get('Pengereman'), f.get('Keterangan_Pengereman',''),
            f.get('Suspensi_Kaki_Kaki'), f.get('Keterangan_Suspensi_Kaki_Kaki',''),
            f.get('Catatan','')
        ))
        mysql.connection.commit()
        
        cur.execute("SELECT Nama_Driver FROM driver WHERE Id_Driver=%s", (id_driver,))
        nd = cur.fetchone()
        nama_driver = nd[0] if nd else "Unknown"
        
        cur.execute("SELECT No_Polisi FROM kendaraan WHERE ID_Kendaraan=%s", (id_kendaraan,))
        np = cur.fetchone()
        plat_nomor = np[0] if np else "Unknown"
        
        kirim_notifikasi_background('inspeksi', nama_driver, plat_nomor)
        cur.close()
        flash('Data inspeksi berhasil disimpan!', 'success')
        return redirect(url_for('inspeksi.list_inspeksi'))

    # Data untuk form
    cur.execute("SELECT ID_Kendaraan, No_Polisi, Merek, Tipe FROM kendaraan ORDER BY No_Polisi")
    kendaraans = cur.fetchall()

    # Driver hanya menautkan ke perjalanan miliknya; admin melihat semua.
    id_driver_login = None
    if session['role'] == 'driver':
        cur.execute("SELECT Id_Driver FROM driver WHERE Id_User = %s", (session['user_id'],))
        row = cur.fetchone()
        id_driver_login = row[0] if row else None

    cur.close()
    return render_template('inspeksi/tambah.html', kendaraans=kendaraans, id_driver_login=id_driver_login)


# =============================================
# HAPUS INSPEKSI
# =============================================
@inspeksi_bp.route('/inspeksi/hapus/<int:id>')
def hapus_inspeksi(id):
    if 'user_id' not in session or session['role'] != 'kepala_operasional_gs':
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('auth.login'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM inspeksi WHERE ID_Inspeksi=%s", (id,))
    mysql.connection.commit()
    cur.close()
    flash('Data inspeksi berhasil dihapus!', 'success')
    return redirect(url_for('inspeksi.list_inspeksi'))


# =============================================
# VERIFIKASI / BATAL VERIFIKASI (ADMIN ONLY)
# =============================================
@inspeksi_bp.route('/inspeksi/verifikasi/<int:id>')
def verifikasi_inspeksi(id):
    if 'user_id' not in session or session['role'] != 'kepala_operasional_gs':
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('auth.login'))
    mysql = get_mysql()
    cur = mysql.connection.cursor()
    set_status_verifikasi(cur, 'inspeksi', 'ID_Inspeksi', id, True, session['user_id'])
    mysql.connection.commit()
    cur.close()
    flash('Data inspeksi berhasil diverifikasi.', 'success')
    return redirect(url_for('inspeksi.list_inspeksi'))


@inspeksi_bp.route('/inspeksi/batal-verifikasi/<int:id>')
def batal_verifikasi_inspeksi(id):
    if 'user_id' not in session or session['role'] != 'kepala_operasional_gs':
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('auth.login'))
    mysql = get_mysql()
    cur = mysql.connection.cursor()
    set_status_verifikasi(cur, 'inspeksi', 'ID_Inspeksi', id, False, session['user_id'])
    mysql.connection.commit()
    cur.close()
    flash('Verifikasi data inspeksi dibatalkan. Data dapat diedit kembali.', 'info')
    return redirect(url_for('inspeksi.list_inspeksi'))


# =============================================
# DETAIL INSPEKSI
# =============================================
@inspeksi_bp.route('/inspeksi/detail/<int:id>')
def detail_inspeksi(id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()
    # i.* dipertahankan (template inspeksi pakai indeks negatif & idx 51 untuk
    # Catatan). Kolom status (i.* idx 52=Status, 53=Waktu, 54=Diverifikasi_Oleh)
    # ikut terbawa tanpa mengganggu indeks negatif kolom join di belakangnya.
    cur.execute("""
        SELECT i.*, d.Nama_Driver, k.No_Polisi
        FROM inspeksi i
        LEFT JOIN driver d ON i.ID_Driver = d.Id_Driver
        LEFT JOIN kendaraan k ON i.ID_Kendaraan = k.ID_Kendaraan
        WHERE i.ID_Inspeksi = %s
    """, (id,))
    inspeksi = cur.fetchone()

    if not inspeksi:
        cur.close()
        flash('Data inspeksi tidak ditemukan.', 'danger')
        return redirect(url_for('inspeksi.list_inspeksi'))

    # R1: driver hanya boleh melihat datanya sendiri (inspeksi[1]=ID_Driver).
    if session.get('role') == 'driver':
        cur.execute("SELECT Id_Driver FROM driver WHERE Id_User = %s", (session['user_id'],))
        r = cur.fetchone()
        if not r or inspeksi[1] != r[0]:
            cur.close()
            flash('Anda hanya dapat melihat data milik Anda sendiri.', 'danger')
            return redirect(url_for('inspeksi.list_inspeksi'))

    status_verifikasi = inspeksi[51]
    waktu_verifikasi  = inspeksi[52]
    verifikator = None
    if inspeksi[53]:
        cur.execute("SELECT Nama FROM user WHERE Id_User = %s", (inspeksi[53],))
        r = cur.fetchone()
        verifikator = r[0] if r else None
    cur.close()
    return render_template('inspeksi/detail.html', inspeksi=inspeksi,
        status_verifikasi=status_verifikasi, waktu_verifikasi=waktu_verifikasi,
        verifikator=verifikator)


# =============================================
# EDIT INSPEKSI
# =============================================
@inspeksi_bp.route('/inspeksi/edit/<int:id>', methods=['GET', 'POST'])
def edit_inspeksi(id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()

    cur.execute("SELECT * FROM inspeksi WHERE ID_Inspeksi=%s", (id,))
    lama = cur.fetchone()
    if not lama:
        cur.close()
        flash('Data inspeksi tidak ditemukan.', 'danger')
        return redirect(url_for('inspeksi.list_inspeksi'))

    # Hak edit terpusat: admin selalu boleh; driver hanya data MILIKNYA yang
    # masih 'Belum'. (lama[1]=ID_Driver, lama[51]=Status_Verifikasi)
    my_id_driver = None
    if session['role'] == 'driver':
        cur.execute("SELECT Id_Driver FROM driver WHERE Id_User = %s", (session['user_id'],))
        row = cur.fetchone()
        my_id_driver = row[0] if row else None
    if not boleh_edit(lama[51], lama[1], session['role'], my_id_driver):
        cur.close()
        if lama[51] == STATUS_TERVERIFIKASI:
            flash('Data sudah diverifikasi admin sehingga tidak dapat diubah.', 'warning')
        else:
            flash('Anda hanya dapat mengedit inspeksi milik Anda sendiri.', 'danger')
        return redirect(url_for('inspeksi.list_inspeksi'))

    if request.method == 'POST':
        f = request.form

        # R2: validasi field wajib + 17 kondisi komponen di sisi server.
        masalah = field_kosong(f, [('Tanggal', 'Tanggal'), ('ID_Kendaraan', 'Kendaraan'), ('Koordinat', 'Koordinat Lokasi')])
        
        for k in KOMPONEN_INSPEKSI:
            kondisi = f.get(k)
            if kondisi not in ('Normal', 'Tidak Normal'):
                if 'Kondisi 17 komponen' not in masalah:
                    masalah.append('Kondisi 17 komponen')
            elif kondisi == 'Tidak Normal':
                ket = f.get(f'Keterangan_{k}')
                if not ket or ket.strip() == '':
                    masalah.append(f'Catatan Kondisi untuk {k.replace("_", " ")}')
                # Untuk Edit: Jika foto lama tidak ada dan tidak ada file baru diunggah, baru tolak
                foto_field = f'Foto_{k}'
                if foto_field in request.files:
                    # Ambil list komponen untuk cek index foto lama
                    # Di fungsi edit, kita perlu mengecek apakah lama memiliki foto untuk field ini
                    # Cara paling sederhana: karena kita sudah menangani ini di HTML required,
                    # Server side validation untuk foto di Edit sedikit lebih kompleks. 
                    # Kita periksa jika file baru kosong DAN lama[idx] juga kosong
                    file = request.files.get(foto_field)
                    idx_mapping = {
                        'Oli_Mesin': 8, 'Oli_Transmisi_Gardan': 11, 'Air_Radiator': 14,
                        'Minyak_Rem': 17, 'V_Belt': 20, 'Body_Exterior': 23, 'Ban': 26,
                        'Interior_Kelengkapan': 29, 'Indikator_Dashboard': 38, 'Asap_Knalpot': 41
                    }
                    if k in idx_mapping:
                        if (not file or file.filename == '') and not lama[idx_mapping[k]]:
                            masalah.append(f'Foto Bukti untuk {k.replace("_", " ")}')

        if masalah:
            cur.close()
            flash('Data wajib belum lengkap: ' + ', '.join(masalah) + '.', 'danger')
            return redirect(url_for('inspeksi.edit_inspeksi', id=id))

        id_kendaraan = f['ID_Kendaraan']
        km_terakhir = get_last_km(cur, id_kendaraan)
        km_kendaraan = int(max(float(f.get('KM_Kendaraan', 0) or 0), km_terakhir))

        # Foto: pakai unggahan baru bila ada, jika tidak pertahankan yang lama.
        def foto(field, prefix, idx_lama):
            return save_foto(request.files.get(field), prefix) or lama[idx_lama]
        fotos = {
            'Foto_Oli_Mesin'            : foto('Foto_Oli_Mesin', 'oli_mesin', 8),
            'Foto_Oli_Transmisi_Gardan' : foto('Foto_Oli_Transmisi_Gardan', 'oli_transmisi', 11),
            'Foto_Air_Radiator'         : foto('Foto_Air_Radiator', 'air_radiator', 14),
            'Foto_Minyak_Rem'           : foto('Foto_Minyak_Rem', 'minyak_rem', 17),
            'Foto_V_Belt'               : foto('Foto_V_Belt', 'v_belt', 20),
            'Foto_Body_Exterior'        : foto('Foto_Body_Exterior', 'body_exterior', 23),
            'Foto_Ban'                  : foto('Foto_Ban', 'ban', 26),
            'Foto_Interior_Kelengkapan' : foto('Foto_Interior_Kelengkapan', 'interior', 29),
            'Foto_Indikator_Dashboard'  : foto('Foto_Indikator_Dashboard', 'dashboard', 38),
            'Foto_Asap_Knalpot'         : foto('Foto_Asap_Knalpot', 'knalpot', 41),
        }

        # Driver tetap pemilik; admin boleh mengganti driver.
        if session['role'] == 'driver':
            id_driver = lama[1]
        else:
            id_driver = f.get('ID_Driver') or lama[1]

        cur.execute("""
            UPDATE inspeksi SET
                ID_Driver=%s, ID_Kendaraan=%s, Tanggal=%s,
                KM_Kendaraan=%s, Koordinat=%s,
                Oli_Mesin=%s, Keterangan_Oli_Mesin=%s, Foto_Oli_Mesin=%s,
                Oli_Transmisi_Gardan=%s, Keterangan_Oli_Transmisi_Gardan=%s, Foto_Oli_Transmisi_Gardan=%s,
                Air_Radiator=%s, Keterangan_Air_Radiator=%s, Foto_Air_Radiator=%s,
                Minyak_Rem=%s, Keterangan_Minyak_Rem=%s, Foto_Minyak_Rem=%s,
                V_Belt=%s, Keterangan_V_Belt=%s, Foto_V_Belt=%s,
                Body_Exterior=%s, Keterangan_Body_Exterior=%s, Foto_Body_Exterior=%s,
                Ban=%s, Keterangan_Ban=%s, Foto_Ban=%s,
                Interior_Kelengkapan=%s, Keterangan_Interior_Kelengkapan=%s, Foto_Interior_Kelengkapan=%s,
                Lampu_Lampu=%s, Keterangan_Lampu_Lampu=%s,
                Suara_Mesin=%s, Keterangan_Suara_Mesin=%s,
                Getaran_Mesin=%s, Keterangan_Getaran_Mesin=%s,
                Indikator_Dashboard=%s, Keterangan_Indikator_Dashboard=%s, Foto_Indikator_Dashboard=%s,
                Asap_Knalpot=%s, Keterangan_Asap_Knalpot=%s, Foto_Asap_Knalpot=%s,
                Transmisi=%s, Keterangan_Transmisi=%s,
                Power_Steering=%s, Keterangan_Power_Steering=%s,
                Pengereman=%s, Keterangan_Pengereman=%s,
                Suspensi_Kaki_Kaki=%s, Keterangan_Suspensi_Kaki_Kaki=%s,
                Catatan=%s
            WHERE ID_Inspeksi=%s
        """, (
            id_driver, id_kendaraan, f['Tanggal'],
            km_kendaraan, f.get('Koordinat', ''),
            f.get('Oli_Mesin'), f.get('Keterangan_Oli_Mesin',''), fotos['Foto_Oli_Mesin'],
            f.get('Oli_Transmisi_Gardan'), f.get('Keterangan_Oli_Transmisi_Gardan',''), fotos['Foto_Oli_Transmisi_Gardan'],
            f.get('Air_Radiator'), f.get('Keterangan_Air_Radiator',''), fotos['Foto_Air_Radiator'],
            f.get('Minyak_Rem'), f.get('Keterangan_Minyak_Rem',''), fotos['Foto_Minyak_Rem'],
            f.get('V_Belt'), f.get('Keterangan_V_Belt',''), fotos['Foto_V_Belt'],
            f.get('Body_Exterior'), f.get('Keterangan_Body_Exterior',''), fotos['Foto_Body_Exterior'],
            f.get('Ban'), f.get('Keterangan_Ban',''), fotos['Foto_Ban'],
            f.get('Interior_Kelengkapan'), f.get('Keterangan_Interior_Kelengkapan',''), fotos['Foto_Interior_Kelengkapan'],
            f.get('Lampu_Lampu'), f.get('Keterangan_Lampu_Lampu',''),
            f.get('Suara_Mesin'), f.get('Keterangan_Suara_Mesin',''),
            f.get('Getaran_Mesin'), f.get('Keterangan_Getaran_Mesin',''),
            f.get('Indikator_Dashboard'), f.get('Keterangan_Indikator_Dashboard',''), fotos['Foto_Indikator_Dashboard'],
            f.get('Asap_Knalpot'), f.get('Keterangan_Asap_Knalpot',''), fotos['Foto_Asap_Knalpot'],
            f.get('Transmisi'), f.get('Keterangan_Transmisi',''),
            f.get('Power_Steering'), f.get('Keterangan_Power_Steering',''),
            f.get('Pengereman'), f.get('Keterangan_Pengereman',''),
            f.get('Suspensi_Kaki_Kaki'), f.get('Keterangan_Suspensi_Kaki_Kaki',''),
            f.get('Catatan',''), id
        ))
        mysql.connection.commit()
        cur.close()
        flash('Data inspeksi berhasil diperbarui!', 'success')
        return redirect(url_for('inspeksi.list_inspeksi'))

    cur.execute("SELECT Id_Driver, Nama_Driver FROM driver ORDER BY Nama_Driver")
    drivers = cur.fetchall()
    cur.execute("SELECT ID_Kendaraan, No_Polisi, Merek, Tipe FROM kendaraan ORDER BY No_Polisi")
    kendaraans = cur.fetchall()
    cur.close()
    return render_template('inspeksi/edit.html', i=lama,
        drivers=drivers, kendaraans=kendaraans)