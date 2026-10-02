"""
Konfigurasi aplikasi terpusat.
Nilai dapat dioverride lewat environment variable agar kredensial tidak
hardcoded di kode (mis. saat deploy). Default cocok untuk XAMPP lokal.
"""
import os


class Config:
    # Keamanan & upload
    SECRET_KEY = os.environ.get('SECRET_KEY', 'hpi_agro_secret_2026')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB

    # Database MySQL
    MYSQL_HOST     = os.environ.get('MYSQL_HOST', 'localhost')
    MYSQL_USER     = os.environ.get('MYSQL_USER', 'root')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
    MYSQL_DB       = os.environ.get('MYSQL_DB', 'db_kendaraan')
