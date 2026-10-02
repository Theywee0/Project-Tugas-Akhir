from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.utils import secure_filename
from models import get_last_km
import os

kendaraan_bp = Blueprint('kendaraan', __name__)

UPLOAD_FOLDER = 'static/uploads/kendaraan'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_mysql():
    from app import mysql
    return mysql

def save_foto(file, prefix):
    """Simpan file foto dan kembalikan nama filenya."""
    if file and file.filename != '' and allowed_file(file.filename):
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        filename = secure_filename(f"{prefix}_{file.filename}")
        file.save(os.path.join(UPLOAD_FOLDER, filename))
        return filename
    return None

# =============================================
# LIST KENDARAAN
# =============================================
@kendaraan_bp.route('/kendaraan')
def list_kendaraan():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM kendaraan ORDER BY ID_Kendaraan DESC")
    data = cur.fetchall()
    cur.close()
    return render_template('kendaraan/list.html', data=data)


# =============================================
# TAMBAH KENDARAAN
# =============================================
@kendaraan_bp.route('/kendaraan/tambah', methods=['GET', 'POST'])
def tambah_kendaraan():
    if 'user_id' not in session or session['role'] != 'kepala_operasional_gs':
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        f = request.form

        # Simpan foto
        foto_depan   = save_foto(request.files.get('Foto_Depan'),   'depan')
        foto_kanan   = save_foto(request.files.get('Foto_Kanan'),   'kanan')
        foto_kiri    = save_foto(request.files.get('Foto_Kiri'),    'kiri')
        foto_belakang= save_foto(request.files.get('Foto_Belakang'),'belakang')
        foto_stnk    = save_foto(request.files.get('Foto_STNK'),    'stnk')

        mysql = get_mysql()
        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO kendaraan (
                No_Polisi, Merek, Tipe, Tahun, Model,
                Kapasitas_Penumpang, Kapasitas_TangkiBBM, Ukuran_Mesin, Jumlah_Slinder, Transmisi,
                SKB, No_Rangka, Jenis_BBM1, Jenis_BBM2, Jenis_BBM3,
                Foto_Depan, Foto_Kanan, Foto_Kiri, Foto_Belakang, Foto_STNK
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            f['No_Polisi'], f['Merek'], f['Tipe'], f['Tahun'], f['Model'],
            f['Kapasitas_Penumpang'], f['Kapasitas_TangkiBBM'], f['Ukuran_Mesin'], f['Jumlah_Slinder'], f['Transmisi'],
            f['SKB'], f['No_Rangka'], f['Jenis_BBM1'], f.get('Jenis_BBM2',''), f.get('Jenis_BBM3',''),
            foto_depan, foto_kanan, foto_kiri, foto_belakang, foto_stnk
        ))
        mysql.connection.commit()
        cur.close()
        flash('Kendaraan berhasil ditambahkan!', 'success')
        return redirect(url_for('kendaraan.list_kendaraan'))

    return render_template('kendaraan/tambah.html')


# =============================================
# EDIT KENDARAAN
# =============================================
@kendaraan_bp.route('/kendaraan/edit/<int:id>', methods=['GET', 'POST'])
def edit_kendaraan(id):
    if 'user_id' not in session or session['role'] != 'kepala_operasional_gs':
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('auth.login'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()

    if request.method == 'POST':
        f = request.form

        # Ambil data lama untuk foto
        cur.execute("SELECT Foto_Depan, Foto_Kanan, Foto_Kiri, Foto_Belakang, Foto_STNK FROM kendaraan WHERE ID_Kendaraan=%s", (id,))
        lama = cur.fetchone()

        foto_depan    = save_foto(request.files.get('Foto_Depan'),   'depan')    or lama[0]
        foto_kanan    = save_foto(request.files.get('Foto_Kanan'),   'kanan')    or lama[1]
        foto_kiri     = save_foto(request.files.get('Foto_Kiri'),    'kiri')     or lama[2]
        foto_belakang = save_foto(request.files.get('Foto_Belakang'),'belakang') or lama[3]
        foto_stnk     = save_foto(request.files.get('Foto_STNK'),    'stnk')     or lama[4]

        cur.execute("""
            UPDATE kendaraan SET
                No_Polisi=%s, Merek=%s, Tipe=%s, Tahun=%s, Model=%s,
                Kapasitas_Penumpang=%s, Kapasitas_TangkiBBM=%s, Ukuran_Mesin=%s, Jumlah_Slinder=%s, Transmisi=%s,
                SKB=%s, No_Rangka=%s, Jenis_BBM1=%s, Jenis_BBM2=%s, Jenis_BBM3=%s,
                Foto_Depan=%s, Foto_Kanan=%s, Foto_Kiri=%s, Foto_Belakang=%s, Foto_STNK=%s
            WHERE ID_Kendaraan=%s
        """, (
            f['No_Polisi'], f['Merek'], f['Tipe'], f['Tahun'], f['Model'],
            f['Kapasitas_Penumpang'], f['Kapasitas_TangkiBBM'], f['Ukuran_Mesin'], f['Jumlah_Slinder'], f['Transmisi'],
            f['SKB'], f['No_Rangka'], f['Jenis_BBM1'], f.get('Jenis_BBM2',''), f.get('Jenis_BBM3',''),
            foto_depan, foto_kanan, foto_kiri, foto_belakang, foto_stnk, id
        ))
        mysql.connection.commit()
        cur.close()
        flash('Data kendaraan berhasil diupdate!', 'success')
        return redirect(url_for('kendaraan.list_kendaraan'))

    cur.execute("SELECT * FROM kendaraan WHERE ID_Kendaraan=%s", (id,))
    kendaraan = cur.fetchone()
    cur.close()
    return render_template('kendaraan/edit.html', kendaraan=kendaraan)


# =============================================
# HAPUS KENDARAAN
# =============================================
@kendaraan_bp.route('/kendaraan/hapus/<int:id>')
def hapus_kendaraan(id):
    if 'user_id' not in session or session['role'] != 'kepala_operasional_gs':
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('auth.login'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()
    cur.execute("DELETE FROM kendaraan WHERE ID_Kendaraan=%s", (id,))
    mysql.connection.commit()
    cur.close()
    flash('Kendaraan berhasil dihapus!', 'success')
    return redirect(url_for('kendaraan.list_kendaraan'))


# =============================================
# API: KM TERAKHIR KENDARAAN (JSON)
# =============================================
@kendaraan_bp.route('/api/kendaraan/<int:id>/km-terakhir')
def api_km_terakhir(id):
    """Endpoint JSON berisi KM terakhir sebuah kendaraan.

    Dipakai oleh form Input Perjalanan & Input BBM untuk mengisi KM awal
    secara otomatis saat kendaraan dipilih. Sumber nilainya tunggal:
    fungsi terpusat get_last_km() (lihat models/__init__.py).
    """
    if 'user_id' not in session:
        return jsonify({'error': 'unauthorized'}), 401

    mysql = get_mysql()
    cur = mysql.connection.cursor()
    km = get_last_km(cur, id)
    cur.close()
    return jsonify({'id_kendaraan': id, 'km_terakhir': km})

# =============================================
# API KHUSUS BBM: KM BBM TERAKHIR (JSON)
# =============================================
@kendaraan_bp.route('/api/kendaraan/<int:id>/km-bbm-terakhir')
def api_km_bbm_terakhir(id):
    """Endpoint JSON berisi KM Akhir terakhir KHUSUS dari tabel BBM.
    
    Dipakai oleh form Input BBM agar tidak mengambil KM perjalanan terakhir,
    melainkan murni KM saat isi bensin sebelumnya (Metode Full-to-Full).
    """
    if 'user_id' not in session:
        return jsonify({'error': 'unauthorized'}), 401

    mysql = get_mysql()
    cur = mysql.connection.cursor()
    cur.execute("SELECT Km_Akhir FROM pengisian_bbm WHERE Id_Kendaraan = %s ORDER BY ID_Pengisian DESC LIMIT 1", (id,))
    row = cur.fetchone()
    km = float(row[0]) if row and row[0] else 0.0
    cur.close()
    return jsonify({'id_kendaraan': id, 'km_bbm_terakhir': km})


# =============================================
# DETAIL KENDARAAN
# =============================================
@kendaraan_bp.route('/kendaraan/detail/<int:id>')
def detail_kendaraan(id):
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM kendaraan WHERE ID_Kendaraan=%s", (id,))
    kendaraan = cur.fetchone()
    cur.close()
    return render_template('kendaraan/detail.html', kendaraan=kendaraan)