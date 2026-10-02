from flask import Blueprint, render_template, request, redirect, url_for, session, flash

kebun_bp = Blueprint('kebun', __name__)


def get_mysql():
    from app import mysql
    return mysql


def admin_only():
    """True jika pengguna adalah admin yang sudah login."""
    return 'user_id' in session and session.get('role') == 'kepala_operasional_gs'


# =============================================
# LIST KEBUN
# =============================================
@kebun_bp.route('/kebun')
def list_kebun():
    if not admin_only():
        flash('Akses ditolak. Halaman ini hanya untuk Admin.', 'danger')
        return redirect(url_for('auth.login'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()
    cur.execute("SELECT Id_Kebun, Nama_Kebun, Alamat, Koordinat FROM kebun ORDER BY Nama_Kebun")
    data = cur.fetchall()
    cur.close()
    return render_template('kebun/list.html', data=data)


# =============================================
# TAMBAH KEBUN
# =============================================
@kebun_bp.route('/kebun/tambah', methods=['GET', 'POST'])
def tambah_kebun():
    if not admin_only():
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        nama = request.form.get('Nama_Kebun', '').strip()
        alamat = request.form.get('Alamat', '').strip()
        koordinat = request.form.get('Koordinat', '').strip()
        if not nama:
            flash('Nama kebun wajib diisi.', 'danger')
            return render_template('kebun/tambah.html')

        mysql = get_mysql()
        cur = mysql.connection.cursor()
        cur.execute("INSERT INTO kebun (Nama_Kebun, Alamat, Koordinat) VALUES (%s, %s, %s)", (nama, alamat, koordinat))
        mysql.connection.commit()
        cur.close()
        flash('Kebun berhasil ditambahkan!', 'success')
        return redirect(url_for('kebun.list_kebun'))

    return render_template('kebun/tambah.html')


# =============================================
# EDIT KEBUN
# =============================================
@kebun_bp.route('/kebun/edit/<int:id>', methods=['GET', 'POST'])
def edit_kebun(id):
    if not admin_only():
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('auth.login'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()

    if request.method == 'POST':
        nama = request.form.get('Nama_Kebun', '').strip()
        alamat = request.form.get('Alamat', '').strip()
        koordinat = request.form.get('Koordinat', '').strip()
        if not nama:
            flash('Nama kebun wajib diisi.', 'danger')
            return redirect(url_for('kebun.edit_kebun', id=id))

        cur.execute("UPDATE kebun SET Nama_Kebun=%s, Alamat=%s, Koordinat=%s WHERE Id_Kebun=%s", (nama, alamat, koordinat, id))
        mysql.connection.commit()
        cur.close()
        flash('Data kebun berhasil diperbarui!', 'success')
        return redirect(url_for('kebun.list_kebun'))

    cur.execute("SELECT Id_Kebun, Nama_Kebun, Alamat, Koordinat FROM kebun WHERE Id_Kebun=%s", (id,))
    kebun = cur.fetchone()
    cur.close()
    if not kebun:
        flash('Data kebun tidak ditemukan.', 'warning')
        return redirect(url_for('kebun.list_kebun'))
    return render_template('kebun/edit.html', kebun=kebun)


# =============================================
# HAPUS KEBUN
# =============================================
@kebun_bp.route('/kebun/hapus/<int:id>')
def hapus_kebun(id):
    if not admin_only():
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('auth.login'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()
    try:
        cur.execute("DELETE FROM kebun WHERE Id_Kebun=%s", (id,))
        mysql.connection.commit()
        flash('Kebun berhasil dihapus!', 'success')
    except Exception:
        # Kebun masih dipakai pada perjalanan/pengisian BBM (foreign key)
        mysql.connection.rollback()
        flash('Kebun tidak dapat dihapus karena masih digunakan pada data perjalanan / pengisian BBM.', 'danger')
    cur.close()
    return redirect(url_for('kebun.list_kebun'))
