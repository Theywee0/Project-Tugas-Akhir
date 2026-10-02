from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
import os

driver_bp = Blueprint('driver', __name__)

UPLOAD_FOLDER = 'static/uploads/driver'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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
# LIST DRIVER
# =============================================
@driver_bp.route('/driver')
def list_driver():
    if 'user_id' not in session or session['role'] != 'kepala_operasional_gs':
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('auth.login'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT d.*, u.Username, u.Nama as Nama_User
        FROM driver d
        LEFT JOIN user u ON d.Id_User = u.Id_User
        ORDER BY d.Id_Driver DESC
    """)
    data = cur.fetchall()
    cur.close()
    return render_template('driver/list.html', data=data)


# =============================================
# TAMBAH DRIVER
# =============================================
@driver_bp.route('/driver/tambah', methods=['GET', 'POST'])
def tambah_driver():
    if 'user_id' not in session or session['role'] != 'kepala_operasional_gs':
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('auth.login'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()

    if request.method == 'POST':
        f = request.form
        foto_profil = save_foto(request.files.get('Foto_Profil'), 'profil')

        # Buat akun user untuk driver dulu (Password otomatis disamakan dengan username)
        from werkzeug.security import generate_password_hash
        username = f.get('username', '').strip()
        password = generate_password_hash(username)

        try:
            cur.execute("""
                INSERT INTO user (Nama, Username, Password, Role)
                VALUES (%s, %s, %s, 'driver')
            """, (f['Nama_Driver'], username, password))
            mysql.connection.commit()
            id_user = cur.lastrowid

            cur.execute("""
                INSERT INTO driver (Id_User, Nama_Driver, Kontak, Kontak_Darurat, Alamat, Foto_Profil)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (id_user, f['Nama_Driver'], f['Kontak'], f['Kontak_Darurat'], f['Alamat'], foto_profil))
            mysql.connection.commit()
            flash('Driver berhasil ditambahkan!', 'success')
        except Exception as e:
            mysql.connection.rollback()
            flash(f'Gagal menambah driver: {str(e)}', 'danger')

        cur.close()
        return redirect(url_for('driver.list_driver'))

    # Ambil user yang belum jadi driver
    cur.execute("""
        SELECT u.Id_User, u.Nama, u.Username FROM user u
        WHERE u.Role = 'driver'
        AND u.Id_User NOT IN (SELECT Id_User FROM driver WHERE Id_User IS NOT NULL)
    """)
    users = cur.fetchall()
    cur.close()
    return render_template('driver/tambah.html', users=users)


# =============================================
# EDIT DRIVER
# =============================================
@driver_bp.route('/driver/edit/<int:id>', methods=['GET', 'POST'])
def edit_driver(id):
    if 'user_id' not in session or session['role'] != 'kepala_operasional_gs':
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('auth.login'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()

    if request.method == 'POST':
        f = request.form

        cur.execute("SELECT Foto_Profil FROM driver WHERE Id_Driver=%s", (id,))
        lama = cur.fetchone()
        foto_profil = save_foto(request.files.get('Foto_Profil'), 'profil') or lama[0]

        cur.execute("""
            UPDATE driver SET
                Nama_Driver=%s, Kontak=%s, Kontak_Darurat=%s, Alamat=%s, Foto_Profil=%s
            WHERE Id_Driver=%s
        """, (f['Nama_Driver'], f['Kontak'], f['Kontak_Darurat'], f['Alamat'], foto_profil, id))
        mysql.connection.commit()
        cur.close()
        flash('Data driver berhasil diupdate!', 'success')
        return redirect(url_for('driver.list_driver'))

    cur.execute("""
        SELECT d.*, u.Username FROM driver d
        LEFT JOIN user u ON d.Id_User = u.Id_User
        WHERE d.Id_Driver=%s
    """, (id,))
    driver = cur.fetchone()
    cur.close()
    return render_template('driver/edit.html', driver=driver)


# =============================================
# HAPUS DRIVER
# =============================================
@driver_bp.route('/driver/hapus/<int:id>')
def hapus_driver(id):
    if 'user_id' not in session or session['role'] != 'kepala_operasional_gs':
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('auth.login'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()

    # Ambil id_user dulu sebelum hapus
    cur.execute("SELECT Id_User FROM driver WHERE Id_Driver=%s", (id,))
    row = cur.fetchone()

    cur.execute("DELETE FROM driver WHERE Id_Driver=%s", (id,))
    if row:
        cur.execute("DELETE FROM user WHERE Id_User=%s AND Role='driver'", (row[0],))
    mysql.connection.commit()
    cur.close()

    flash('Driver berhasil dihapus!', 'success')
    return redirect(url_for('driver.list_driver'))


# =============================================
# DETAIL DRIVER
# =============================================
@driver_bp.route('/driver/detail/<int:id>')
def detail_driver(id):
    if 'user_id' not in session or session['role'] != 'kepala_operasional_gs':
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('auth.login'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT d.*, u.Username FROM driver d
        LEFT JOIN user u ON d.Id_User = u.Id_User
        WHERE d.Id_Driver=%s
    """, (id,))
    driver = cur.fetchone()
    
    # Ambil riwayat operasional
    cur.execute("""
        SELECT p.Tanggal, k.No_Polisi, k1.Nama_Kebun AS Asal, k2.Nama_Kebun AS Tujuan, p.Jumlah_KM
        FROM perjalanan p
        LEFT JOIN kendaraan k ON p.ID_Kendaraan = k.ID_Kendaraan
        LEFT JOIN kebun k1 ON p.ID_Kebun_Asal = k1.ID_Kebun
        LEFT JOIN kebun k2 ON p.ID_Kebun_Tujuan = k2.ID_Kebun
        WHERE p.ID_Driver=%s ORDER BY p.Tanggal DESC
    """, (id,))
    perjalanan = cur.fetchall()
    
    cur.execute("""
        SELECT b.Tanggal, k.No_Polisi, b.Jenis_BBM, b.Jumlah_BBM
        FROM pengisian_bbm b
        LEFT JOIN kendaraan k ON b.Id_Kendaraan = k.ID_Kendaraan
        WHERE b.Id_Driver=%s ORDER BY b.Tanggal DESC
    """, (id,))
    bbm = cur.fetchall()
    
    cur.execute("""
        SELECT i.Tanggal, k.No_Polisi, i.Catatan
        FROM inspeksi i
        LEFT JOIN kendaraan k ON i.ID_Kendaraan = k.ID_Kendaraan
        WHERE i.ID_Driver=%s ORDER BY i.Tanggal DESC
    """, (id,))
    inspeksi = cur.fetchall()
    
    cur.execute("""
        SELECT m.Tanggal, k.No_Polisi, m.Lokasi_Maintenance, m.Keluhan, m.Spareparts
        FROM maintenance m
        LEFT JOIN kendaraan k ON m.ID_Kendaraan = k.ID_Kendaraan
        WHERE m.ID_Driver=%s ORDER BY m.Tanggal DESC
    """, (id,))
    maintenance = cur.fetchall()
    
    cur.close()
    return render_template('driver/detail.html', driver=driver, perjalanan=perjalanan, bbm=bbm, inspeksi=inspeksi, maintenance=maintenance)