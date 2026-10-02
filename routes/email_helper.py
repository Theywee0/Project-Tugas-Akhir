import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import threading
import logging
from datetime import datetime

# Konfigurasi Akun Pengirim (Tanam disini sesuai Best Practice)
EMAIL_PENGIRIM = "theywee0415@gmail.com"
EMAIL_PENERIMA = "theywee0415@gmail.com"
PASSWORD_APLIKASI = "eudldbllrvbvpyra"

def _kirim_email_async(modul, nama_driver, plat_nomor):
    """Fungsi internal untuk mengirim email di background."""
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_PENGIRIM
        msg["To"] = EMAIL_PENERIMA
        msg["Subject"] = f"Laporan {modul.capitalize()} Baru - {nama_driver}"
        
        waktu_sekarang = datetime.now().strftime("%d-%m-%Y %H:%M")

        # Menggunakan format HTML agar bisa menebalkan huruf (Bold)
        body = f"""
<html>
<body>
<p>Yth. Kepala Operasional General Service,</p>

<p>Pemberitahuan bahwa ada laporan <b>{modul.capitalize()}</b> baru yang memerlukan tindakan verifikasi Anda.</p>

<p><b>Rincian Laporan:</b><br>
Modul: {modul.capitalize()}<br>
Kendaraan: {plat_nomor}<br>
Waktu Input: {waktu_sekarang}</p>

<p>Mohon segera periksa data tersebut melalui menu Dashboard / Data Menunggu Verifikasi pada aplikasi web.</p>

<p>Terima kasih,<br>
Sistem Operasional GS</p>
</body>
</html>
"""
        msg.attach(MIMEText(body, "html"))

        # Menyambung ke server Gmail SMTP
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(EMAIL_PENGIRIM, PASSWORD_APLIKASI)
        server.send_message(msg)
        server.quit()
        logging.info(f"Email notifikasi {modul} berhasil dikirim.")
    except Exception as e:
        logging.error(f"Gagal mengirim email notifikasi {modul}: {str(e)}")

def kirim_notifikasi_background(modul, nama_driver, plat_nomor):
    """
    Membuka thread baru agar pengiriman email tidak membuat web loading lama.
    modul: "Perjalanan", "BBM", "Maintenance", "Inspeksi"
    """
    thread = threading.Thread(target=_kirim_email_async, args=(modul, nama_driver, plat_nomor))
    thread.daemon = True
    thread.start()

