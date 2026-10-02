"""
Logika data terpusat (shared) yang dipakai lintas modul.

Tujuan utama paket ini adalah menghindari duplikasi query dan menjaga
agar perhitungan yang sama selalu konsisten di seluruh aplikasi —
khususnya "KM terakhir kendaraan" yang sebelumnya dihitung sendiri-sendiri
oleh modul perjalanan, pengisian BBM, dan maintenance.
"""


# =====================================================================
# KM KENDARAAN — SATU SUMBER KEBENARAN LINTAS MODUL
# =====================================================================
def get_last_km(cur, id_kendaraan):
    """KM (odometer) TERAKHIR sebuah kendaraan, sebagai satu sumber kebenaran.

    KM terakhir = nilai odometer tertinggi yang pernah tercatat pada
    kendaraan tersebut di SELURUH modul operasional:
      - perjalanan.KM_Akhir     (KM setelah perjalanan)
      - pengisian_bbm.Km_Akhir  (KM saat pengisian BBM)
      - maintenance.KM_Kendaraan(KM saat maintenance)

    Dengan mengambil nilai MAX dari ketiganya, KM kendaraan menjadi satu
    garis waktu yang konsisten dan tidak pernah mundur, apa pun modul
    terakhir yang mencatatnya.

    :param cur: cursor MySQL yang sedang aktif
    :param id_kendaraan: ID kendaraan (boleh None / kosong)
    :return: float KM terakhir, atau 0.0 bila kendaraan belum punya riwayat
    """
    if not id_kendaraan:
        return 0.0
    cur.execute(
        """
        SELECT MAX(km) FROM (
            SELECT MAX(KM_Akhir)      AS km FROM perjalanan    WHERE ID_Kendaraan = %s
            UNION ALL
            SELECT MAX(Km_Akhir)      AS km FROM pengisian_bbm WHERE Id_Kendaraan = %s
            UNION ALL
            SELECT MAX(KM_Kendaraan)  AS km FROM maintenance   WHERE ID_Kendaraan = %s
        ) AS riwayat_km
        """,
        (id_kendaraan, id_kendaraan, id_kendaraan),
    )
    row = cur.fetchone()
    return float(row[0]) if row and row[0] is not None else 0.0


# =====================================================================
# FILTER PERIODE — DIPAKAI DASHBOARD UNTUK MENGONTROL STATISTIK
# =====================================================================
# Urutan sengaja dari rentang tersempit ke terluas (tampil rapi di UI).
PERIODE_OPSI = ('hari', 'minggu', 'bulan', 'tahun')
PERIODE_LABEL = {
    'hari':   'Hari Ini',
    'minggu': 'Minggu Ini',
    'bulan':  'Bulan Ini',
    'tahun':  'Tahun Ini',
}
PERIODE_DEFAULT = 'bulan'


def normalisasi_periode(periode):
    """Pastikan nilai periode valid; nilai tak dikenal -> PERIODE_DEFAULT."""
    return periode if periode in PERIODE_OPSI else PERIODE_DEFAULT


def periode_clause(periode, kolom='Tanggal'):
    """Potongan klausa SQL (tanpa kata 'WHERE') untuk memfilter sebuah kolom
    tanggal berdasarkan periode terpilih, relatif terhadap tanggal database
    hari ini (CURDATE()).

    Aman dari SQL injection: `periode` selalu dinormalisasi ke whitelist dan
    `kolom` hanya diisi nilai tetap dari kode (bukan input pengguna).

    :param periode: salah satu dari PERIODE_OPSI
    :param kolom: nama kolom tanggal yang difilter
    :return: string kondisi SQL siap pakai
    """
    periode = normalisasi_periode(periode)
    if periode == 'hari':
        return f"DATE({kolom}) = CURDATE()"
    if periode == 'minggu':
        # mode 1: minggu dimulai hari Senin (konsisten kalender Indonesia)
        return f"YEARWEEK({kolom}, 1) = YEARWEEK(CURDATE(), 1)"
    if periode == 'tahun':
        return f"YEAR({kolom}) = YEAR(CURDATE())"
    # default: bulan berjalan
    return f"MONTH({kolom}) = MONTH(CURDATE()) AND YEAR({kolom}) = YEAR(CURDATE())"


# =====================================================================
# STATUS VERIFIKASI — KENDALI HAK EDIT & KUALITAS DATA ANALISIS
# =====================================================================
# Data dari driver berstatus 'Belum' (masih bisa dikoreksi pemiliknya).
# Setelah admin memverifikasi -> 'Terverifikasi' (terkunci dari driver) dan
# hanya data 'Terverifikasi' yang dipakai pada clustering & laporan (Opsi 10-B).
STATUS_BELUM = 'Belum'
STATUS_TERVERIFIKASI = 'Terverifikasi'


def boleh_edit(status, id_driver_pemilik, role, my_id_driver):
    """Aturan terpusat siapa yang boleh mengedit sebuah data operasional.

    - Admin: selalu boleh (otoritas koreksi / data steward).
    - Driver: hanya bila data MILIKNYA sendiri DAN masih 'Belum' diverifikasi.

    Dipakai baik di backend (penegakan) maupun template (tampil/sembunyi tombol)
    agar logikanya tunggal dan tidak terduplikasi di tiap modul.
    """
    if role == 'admin':
        return True
    return (id_driver_pemilik == my_id_driver) and (status == STATUS_BELUM)


def set_status_verifikasi(cur, tabel, pk_col, pk_val, terverifikasi, user_id):
    """Set status verifikasi sebuah record sekaligus mencatat audit ringan
    (waktu & pelaku). `tabel` dan `pk_col` berasal dari kode (aman), nilai
    selalu lewat parameter %s.

    :param terverifikasi: True -> kunci ('Terverifikasi'); False -> buka ('Belum')
    :param user_id: Id_User admin yang melakukan aksi
    """
    if terverifikasi:
        cur.execute(
            f"UPDATE {tabel} SET Status_Verifikasi=%s, Waktu_Verifikasi=NOW(), "
            f"Diverifikasi_Oleh=%s WHERE {pk_col}=%s",
            (STATUS_TERVERIFIKASI, user_id, pk_val))
    else:
        cur.execute(
            f"UPDATE {tabel} SET Status_Verifikasi=%s, Waktu_Verifikasi=NULL, "
            f"Diverifikasi_Oleh=NULL WHERE {pk_col}=%s",
            (STATUS_BELUM, pk_val))


def field_kosong(form, wajib):
    """Validasi server-side: kembalikan daftar LABEL field wajib yang kosong/absen
    pada form. Dipakai agar form tidak bisa dilewati walau validasi klien (HTML5
    `required`) dimanipulasi.

    :param form: request.form
    :param wajib: list pasangan (nama_field, label_tampilan)
    :return: list label yang kosong (list kosong = semua terisi/valid)
    """
    return [label for nama, label in wajib if not (form.get(nama) or '').strip()]


def filter_terverifikasi(alias=''):
    """Potongan klausa SQL untuk membatasi analisis/laporan HANYA pada data
    yang sudah 'Terverifikasi' (Opsi 10-B). `alias` = prefix tabel bila perlu
    (mis. 'p' -> 'p.Status_Verifikasi ...'). Aman: tanpa input pengguna.
    """
    prefix = f"{alias}." if alias else ''
    return f"{prefix}Status_Verifikasi = '{STATUS_TERVERIFIKASI}'"
