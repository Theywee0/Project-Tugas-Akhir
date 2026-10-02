from flask import Flask, redirect, url_for, session
from flask_mysqldb import MySQL
import os

app = Flask(__name__)

# Konfigurasi dimuat terpusat dari config.py (mendukung override via env var)
from config import Config
app.config.from_object(Config)

mysql = MySQL(app)
app.extensions['mysql'] = mysql

# ============= IMPOR BLUEPRINT =============
from routes.auth        import auth_bp
from routes.kendaraan   import kendaraan_bp
from routes.driver      import driver_bp
from routes.perjalanan  import perjalanan_bp
from routes.bbm         import bbm_bp
from routes.inspeksi    import inspeksi_bp
from routes.maintenance import maintenance_bp
from routes.laporan     import laporan_bp
from routes.clustering  import clustering_bp
from routes.kebun       import kebun_bp
from routes.user        import user_bp

# ============= REGISTRASI BLUEPRINT =============
app.register_blueprint(auth_bp)
app.register_blueprint(kendaraan_bp)
app.register_blueprint(driver_bp)
app.register_blueprint(perjalanan_bp)
app.register_blueprint(bbm_bp)
app.register_blueprint(inspeksi_bp)
app.register_blueprint(maintenance_bp)
app.register_blueprint(laporan_bp)
app.register_blueprint(clustering_bp)
app.register_blueprint(kebun_bp)
app.register_blueprint(user_bp)

# ============= ROUTE UTAMA =============
@app.route('/')
def index():
    """Redirect ke halaman yang sesuai berdasarkan role pengguna."""
    if 'user_id' in session:
        if session.get('role') == 'admin':
            return redirect(url_for('laporan.dashboard_admin'))
        elif session.get('role') == 'driver':
            return redirect(url_for('auth.dashboard_driver'))
    return redirect(url_for('auth.login'))

# ============= ERROR HANDLER =============
@app.errorhandler(404)
def not_found(e):
    return "Halaman tidak ditemukan.", 404

@app.errorhandler(500)
def internal_error(e):
    return "Terjadi kesalahan pada server. Silakan coba lagi nanti.", 500

# ============= MENJALANKAN APLIKASI =============
if __name__ == '__main__':
    app.run(debug=True)