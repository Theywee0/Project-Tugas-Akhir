from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash

user_bp = Blueprint('user', __name__)


def get_mysql():
    from app import mysql
    return mysql


def user_management_allowed():
    return 'user_id' in session and session.get('role') in ['admin', 'kepala_operasional_gs']

# =============================================
# LIST USER
# =============================================
@user_bp.route('/user')
def list_user():
    if not user_management_allowed():
        flash('Akses ditolak. Halaman ini khusus Admin dan Kepala Operasional GS.', 'danger')
        return redirect(url_for('auth.login'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT u.Id_User, u.Nama, u.Username, u.Role, u.Created_At,
               CASE WHEN d.Id_Driver IS NULL THEN 0 ELSE 1 END AS is_driver
        FROM user u
        LEFT JOIN driver d ON u.Id_User = d.Id_User
        ORDER BY u.Role, u.Nama
    """)
    data = cur.fetchall()
    cur.close()
    return render_template('user/list.html', data=data)


# =============================================
# TAMBAH USER
# =============================================
@user_bp.route('/user/tambah', methods=['GET', 'POST'])
def tambah_user():
    if not user_management_allowed():
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        f = request.form
        nama     = f.get('Nama', '').strip()
        username = f.get('Username', '').strip()
        password = f.get('Password', '')
        role     = f.get('Role', 'driver')

        if not nama or not username or not password:
            flash('Nama, username, dan password wajib diisi.', 'danger')
            return render_template('user/tambah.html')
            
        import re
        if len(password) < 8 or not re.search(r'[A-Z]', password) or not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            flash('Password tidak memenuhi syarat keamanan (min 8 karakter, 1 huruf kapital, 1 simbol).', 'danger')
            return render_template('user/tambah.html')
            
        if role not in ('admin', 'kepala_operasional_gs', 'driver'):
            role = 'driver'
            
        # Kepala GS hanya boleh membuat akun driver
        if session.get('role') == 'kepala_operasional_gs' and role != 'driver':
            role = 'driver'

        mysql = get_mysql()
        cur = mysql.connection.cursor()
        try:
            cur.execute(
                "INSERT INTO user (Nama, Username, Password, Role, is_first_login) VALUES (%s, %s, %s, %s, 1)",
                (nama, username, generate_password_hash(password), role)
            )
            mysql.connection.commit()
            flash('User berhasil ditambahkan!', 'success')
            cur.close()
            return redirect(url_for('user.list_user'))
        except Exception:
            mysql.connection.rollback()
            cur.close()
            flash('Gagal menambah user. Username mungkin sudah digunakan.', 'danger')
            return render_template('user/tambah.html')

    return render_template('user/tambah.html')


# =============================================
# EDIT USER
# =============================================
@user_bp.route('/user/edit/<int:id>', methods=['GET', 'POST'])
def edit_user(id):
    if not user_management_allowed():
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('auth.login'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()

    # Ambil data user yang sedang diedit
    cur.execute("SELECT Id_User, Nama, Username, Role FROM user WHERE Id_User=%s", (id,))
    user = cur.fetchone()
    
    if not user:
        cur.close()
        flash('User tidak ditemukan.', 'warning')
        return redirect(url_for('user.list_user'))

    if request.method == 'POST':
        f = request.form
        nama     = f.get('Nama', '').strip()
        username = f.get('Username', '').strip()
        role     = f.get('Role', 'driver')
        password = f.get('Password', '')  # kosong = tidak diubah

        if not nama or not username:
            flash('Nama dan username wajib diisi.', 'danger')
            return redirect(url_for('user.edit_user', id=id))
            
        import re
        if password:
            if len(password) < 8 or not re.search(r'[A-Z]', password) or not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
                flash('Password baru tidak memenuhi syarat keamanan (min 8 karakter, 1 huruf kapital, 1 simbol).', 'danger')
                return redirect(url_for('user.edit_user', id=id))
            
        if role not in ('admin', 'kepala_operasional_gs', 'driver'):
            role = 'driver'

        # Validasi khusus Kepala GS:
        # 1. Tidak boleh mengedit user selain driver
        # 2. Tidak boleh mengubah password
        # 3. Tidak boleh mengangkat driver menjadi admin/kepala
        if session.get('role') == 'kepala_operasional_gs':
            if user[3] != 'driver':
                flash('Akses ditolak. Anda hanya berhak mengedit akun Driver.', 'danger')
                return redirect(url_for('user.list_user'))
            if password:
                flash('Modifikasi ditolak. Anda tidak berhak mengubah password.', 'danger')
                return redirect(url_for('user.edit_user', id=id))
            if role != 'driver':
                role = 'driver'

        try:
            if password:
                cur.execute(
                    "UPDATE user SET Nama=%s, Username=%s, Role=%s, Password=%s, is_first_login=1 WHERE Id_User=%s",
                    (nama, username, role, generate_password_hash(password), id)
                )
            else:
                cur.execute(
                    "UPDATE user SET Nama=%s, Username=%s, Role=%s WHERE Id_User=%s",
                    (nama, username, role, id)
                )
            mysql.connection.commit()
            flash('Data user berhasil diperbarui!', 'success')
            cur.close()
            return redirect(url_for('user.list_user'))
        except Exception:
            mysql.connection.rollback()
            cur.close()
            flash('Gagal memperbarui user. Username mungkin sudah digunakan.', 'danger')
            return redirect(url_for('user.edit_user', id=id))

    cur.close()
    return render_template('user/edit.html', user=user)


# =============================================
# HAPUS USER
# =============================================
@user_bp.route('/user/hapus/<int:id>')
def hapus_user(id):
    if not user_management_allowed():
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('auth.login'))

    # Cegah menghapus akunnya sendiri
    if id == session.get('user_id'):
        flash('Anda tidak dapat menghapus akun yang sedang digunakan.', 'warning')
        return redirect(url_for('user.list_user'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()
    
    # Ambil data target untuk validasi Kepala GS
    cur.execute("SELECT Role FROM user WHERE Id_User=%s", (id,))
    target = cur.fetchone()
    
    if target and session.get('role') == 'kepala_operasional_gs' and target[0] != 'driver':
        cur.close()
        flash('Akses ditolak. Anda hanya berhak menghapus akun Driver.', 'danger')
        return redirect(url_for('user.list_user'))

    try:
        # Hapus data driver yang terkait dulu (jika ada) agar konsisten
        cur.execute("DELETE FROM driver WHERE Id_User=%s", (id,))
        cur.execute("DELETE FROM user WHERE Id_User=%s", (id,))
        mysql.connection.commit()
        flash('User berhasil dihapus!', 'success')
    except Exception:
        mysql.connection.rollback()
        flash('User tidak dapat dihapus karena masih memiliki data terkait (perjalanan/BBM).', 'danger')
    cur.close()
    return redirect(url_for('user.list_user'))
