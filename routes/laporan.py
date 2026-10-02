from flask import Blueprint, render_template, request, redirect, url_for, session, flash
import json
import datetime

laporan_bp = Blueprint('laporan', __name__)

# Nama bulan Bahasa Indonesia (indeks 1-12) untuk label periode dashboard.
BULAN_ID = ['', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni',
            'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember']

def get_mysql():
    from app import mysql
    return mysql

def admin_required():
    if 'user_id' not in session or session['role'] not in ['kepala_operasional_gs', 'admin']:
        return False
    return True


# =============================================
# DASHBOARD ADMIN
# =============================================
@laporan_bp.route('/dashboard/admin')
def dashboard_admin():
    if not admin_required():
        return redirect(url_for('auth.login'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()

    cur.execute("SELECT COUNT(*) FROM kendaraan")
    total_kendaraan = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM driver")
    total_driver = cur.fetchone()[0]

    # ============================================================
    # PERIODE AKTIF DASHBOARD
    # ============================================================
    _t = datetime.date.today()
    periode_awal = _t.replace(day=1)
    _next = (periode_awal.replace(year=periode_awal.year + 1, month=1)
             if periode_awal.month == 12
             else periode_awal.replace(month=periode_awal.month + 1))
    periode_akhir = _next - datetime.timedelta(days=1)
    
    cur.execute("SELECT COUNT(*) FROM hasil_cluster")
    ada_clustering = cur.fetchone()[0] > 0

    # Periode setara sebelumnya: rentang sama panjang tepat sebelum periode aktif.
    _panjang = (periode_akhir - periode_awal).days + 1
    prev_akhir = periode_awal - datetime.timedelta(days=1)
    prev_awal  = prev_akhir - datetime.timedelta(days=_panjang - 1)

    # statistik operasional HANYA dari data Terverifikasi, pada periode aktif.
    def _sum_periode(tabel, kolom, pa, pk):
        cur.execute(
            f"SELECT COALESCE(SUM({kolom}), 0) FROM {tabel} "
            f"WHERE Tanggal BETWEEN %s AND %s AND Status_Verifikasi = 'Terverifikasi'",
            (pa, pk))
        return float(cur.fetchone()[0])

    total_bbm_bulan   = _sum_periode('pengisian_bbm', 'Jumlah_BBM', periode_awal, periode_akhir)
    total_bbm_lalu    = _sum_periode('pengisian_bbm', 'Jumlah_BBM', prev_awal, prev_akhir)
    
    # Total jarak harus menjumlahkan Jarak dari Perjalanan dan Jarak dari Pengisian BBM
    total_jarak_bulan = _sum_periode('perjalanan', 'Jumlah_KM', periode_awal, periode_akhir) + \
                        _sum_periode('pengisian_bbm', 'Jumlah_Km', periode_awal, periode_akhir)
                        
    total_jarak_lalu  = _sum_periode('perjalanan', 'Jumlah_KM', prev_awal, prev_akhir) + \
                        _sum_periode('pengisian_bbm', 'Jumlah_Km', prev_awal, prev_akhir)

    # Rata-rata rasio: hasil clustering pada seluruh riwayat.
    cur.execute("SELECT COALESCE(AVG(Rasio_Konsumsi), 0) FROM hasil_cluster")
    rata_rasio = cur.fetchone()[0]

    # Jumlah kendaraan yang MASUK analisis clustering
    cur.execute("SELECT COUNT(DISTINCT Id_Kendaraan) FROM hasil_cluster")
    kendaraan_dianalisis = int(cur.fetchone()[0])

    # GRAFIK BBM per bulan — DI DALAM periode aktif (maks 12 bulan terakhir) ===
    cur.execute("""
        SELECT DATE_FORMAT(Tanggal, '%%b %%Y'), YEAR(Tanggal), MONTH(Tanggal),
               COALESCE(SUM(Jumlah_BBM), 0)
        FROM pengisian_bbm
        WHERE Tanggal BETWEEN %s AND %s AND Status_Verifikasi = 'Terverifikasi'
        GROUP BY YEAR(Tanggal), MONTH(Tanggal), DATE_FORMAT(Tanggal, '%%b %%Y')
        ORDER BY YEAR(Tanggal), MONTH(Tanggal)
    """, (periode_awal, periode_akhir))
    rows_bbm = cur.fetchall()[-12:]
    grafik_label = json.dumps([r[0] for r in rows_bbm]) if rows_bbm else json.dumps([])
    grafik_data  = json.dumps([float(r[3]) for r in rows_bbm]) if rows_bbm else json.dumps([])

    # DISTRIBUSI KONDISI — analisis terakhir yang dijalankan ===
    cur.execute("""
        SELECT Kategori, COUNT(*) as jml
        FROM hasil_cluster
        GROUP BY Kategori
    """)
    klaster_rows = cur.fetchall()
    klaster_data = {}
    for row in klaster_rows:
        if row[0]: # Pastikan tidak None
            klaster_data[row[0]] = row[1]

    # TABEL KENDARAAN + STATUS KONDISI — periode aktif (analisis terakhir) ===
    cur.execute("""
        SELECT k.No_Polisi, k.Merek, k.Tipe,
               COALESCE(hc.Total_Jarak, 0),
               COALESCE(hc.Total_Bbm, 0),
               COALESCE(hc.Rasio_Konsumsi, 0),
               COALESCE(hc.Kategori, 'Belum Dianalisis')
        FROM kendaraan k
        LEFT JOIN hasil_cluster hc ON k.ID_Kendaraan = hc.Id_Kendaraan
        ORDER BY k.No_Polisi
    """)
    tabel_kendaraan = cur.fetchall()

    # === DATA MENUNGGU VERIFIKASI (Status_Verifikasi='Belum') per modul ===
    # Hanya COUNT read-only; menjadikan dashboard sebagai titik aksi admin.
    pending = {}
    for key, tabel in [('perjalanan', 'perjalanan'), ('bbm', 'pengisian_bbm'),
                       ('maintenance', 'maintenance'), ('inspeksi', 'inspeksi')]:
        cur.execute(f"SELECT COUNT(*) FROM {tabel} WHERE Status_Verifikasi = 'Belum'")
        pending[key] = int(cur.fetchone()[0])
    pending['total'] = pending['perjalanan'] + pending['bbm'] + pending['maintenance'] + pending['inspeksi']

    cur.close()

    pct_bbm   = round(((total_bbm_bulan - total_bbm_lalu) / total_bbm_lalu) * 100, 1) if total_bbm_lalu > 0 else 0
    pct_jarak = round(((total_jarak_bulan - total_jarak_lalu) / total_jarak_lalu) * 100, 1) if total_jarak_lalu > 0 else 0

    # Label periode: rentang tanggal bila mengikuti clustering; bulan berjalan bila fallback.
    def _fmt_tgl(d):
        return f"{d.day} {BULAN_ID[d.month]} {d.year}"
    periode_label = f"{BULAN_ID[periode_awal.month]} {periode_awal.year} (bulan berjalan)"

    stats = {
        'total_kendaraan'  : total_kendaraan,
        'total_driver'     : total_driver,
        'total_bbm_bulan'  : round(float(total_bbm_bulan), 1),
        'pct_bbm'          : pct_bbm,
        'total_jarak_bulan': round(float(total_jarak_bulan), 1),
        'pct_jarak'        : pct_jarak,
        'rata_rasio'       : round(float(rata_rasio), 3),
        'klaster_data'     : klaster_data,
        'grafik_label'     : grafik_label,
        'grafik_data'      : grafik_data,
        'tabel_kendaraan'  : tabel_kendaraan,
        'pending'          : pending,
        'periode_label'    : periode_label,
        'ada_clustering'   : ada_clustering,
        'kendaraan_dianalisis' : kendaraan_dianalisis,
    }
    return render_template('laporan/dashboard.html', stats=stats)


# =============================================
# LAPORAN PERJALANAN
# =============================================
@laporan_bp.route('/laporan/perjalanan')
def laporan_perjalanan():
    if not admin_required():
        return redirect(url_for('auth.login'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()

    bulan = request.args.get('bulan', '')
    tahun = request.args.get('tahun', '')

    query = """
        SELECT p.ID_Perjalanan, p.Tanggal, p.Jam,
               d.Nama_Driver, k.No_Polisi, k.Merek, k.Tipe,
               kb1.Nama_Kebun, kb2.Nama_Kebun,
               p.KM_Awal, p.KM_Akhir, p.Jumlah_KM,
               p.Nama_Penumpang, p.Keterangan
        FROM perjalanan p
        LEFT JOIN driver d ON p.ID_Driver = d.Id_Driver
        LEFT JOIN kendaraan k ON p.ID_Kendaraan = k.ID_Kendaraan
        LEFT JOIN kebun kb1 ON p.ID_Kebun_Asal = kb1.Id_Kebun
        LEFT JOIN kebun kb2 ON p.ID_Kebun_Tujuan = kb2.Id_Kebun
    """
    params = []
    # Opsi 10-B: laporan hanya menampilkan data yang sudah Terverifikasi.
    conditions = ["p.Status_Verifikasi = 'Terverifikasi'"]
    if bulan:
        conditions.append("MONTH(p.Tanggal) = %s")
        params.append(bulan)
    if tahun:
        conditions.append("YEAR(p.Tanggal) = %s")
        params.append(tahun)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY p.Tanggal DESC, p.Jam DESC"
    cur.execute(query, params)
    data = cur.fetchall()

    # Statistik — query terpisah sesuai filter
    stat_query = "SELECT COUNT(*), COALESCE(SUM(Jumlah_KM),0), COALESCE(AVG(Jumlah_KM),0) FROM perjalanan"
    stat_params = []
    stat_conditions = ["Status_Verifikasi = 'Terverifikasi'"]
    if bulan:
        stat_conditions.append("MONTH(Tanggal) = %s")
        stat_params.append(bulan)
    if tahun:
        stat_conditions.append("YEAR(Tanggal) = %s")
        stat_params.append(tahun)
    if stat_conditions:
        stat_query += " WHERE " + " AND ".join(stat_conditions)
    cur.execute(stat_query, stat_params)
    stat = cur.fetchone()

    cur.close()
    return render_template('laporan/perjalanan.html',
        data=data, stat=stat, bulan=bulan, tahun=tahun)


# =============================================
# LAPORAN BBM
# =============================================
@laporan_bp.route('/laporan/bbm')
def laporan_bbm():
    if not admin_required():
        return redirect(url_for('auth.login'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()

    bulan = request.args.get('bulan', '')
    tahun = request.args.get('tahun', '')

    # Query detail
    query = """
        SELECT b.Id_Pengisian, b.Tanggal, b.Jam,
               d.Nama_Driver, k.No_Polisi, k.Merek, k.Tipe,
               kb.Nama_Kebun, b.Jenis_BBM, b.Jumlah_BBM,
               b.Km_Awal, b.Km_Akhir, b.Jumlah_Km, b.Koordinat
        FROM pengisian_bbm b
        LEFT JOIN driver d ON b.Id_Driver = d.Id_Driver
        LEFT JOIN kendaraan k ON b.Id_Kendaraan = k.ID_Kendaraan
        LEFT JOIN kebun kb ON b.Id_Kebun = kb.Id_Kebun
    """
    params = []
    # Opsi 10-B: laporan hanya menampilkan data yang sudah Terverifikasi.
    conditions = ["b.Status_Verifikasi = 'Terverifikasi'"]
    if bulan:
        conditions.append("MONTH(b.Tanggal) = %s")
        params.append(bulan)
    if tahun:
        conditions.append("YEAR(b.Tanggal) = %s")
        params.append(tahun)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY b.Tanggal DESC"
    cur.execute(query, params)
    data = cur.fetchall()

    # Statistik per kendaraan — query terpisah sesuai filter
    stat_base = """
        SELECT k.No_Polisi, k.Merek, k.Tipe,
               COUNT(b.Id_Pengisian),
               COALESCE(SUM(b.Jumlah_BBM),0),
               COALESCE(SUM(b.Jumlah_Km),0),
               CASE WHEN SUM(b.Jumlah_Km) > 0
                    THEN ROUND(SUM(b.Jumlah_BBM)/SUM(b.Jumlah_Km),3)
                    ELSE 0 END
        FROM pengisian_bbm b
        LEFT JOIN kendaraan k ON b.Id_Kendaraan = k.ID_Kendaraan
    """
    s_params = []
    s_cond = ["b.Status_Verifikasi = 'Terverifikasi'"]
    if bulan:
        s_cond.append("MONTH(b.Tanggal) = %s")
        s_params.append(bulan)
    if tahun:
        s_cond.append("YEAR(b.Tanggal) = %s")
        s_params.append(tahun)
    if s_cond:
        stat_base += " WHERE " + " AND ".join(s_cond)
    stat_base += " GROUP BY k.ID_Kendaraan, k.No_Polisi, k.Merek, k.Tipe ORDER BY 5 DESC"
    cur.execute(stat_base, s_params)
    stat_kendaraan = cur.fetchall()

    # Total keseluruhan
    total_query = "SELECT COUNT(*), COALESCE(SUM(Jumlah_BBM),0), COALESCE(SUM(Jumlah_Km),0) FROM pengisian_bbm"
    t_params = []
    t_cond = ["Status_Verifikasi = 'Terverifikasi'"]
    if bulan:
        t_cond.append("MONTH(Tanggal) = %s")
        t_params.append(bulan)
    if tahun:
        t_cond.append("YEAR(Tanggal) = %s")
        t_params.append(tahun)
    if t_cond:
        total_query += " WHERE " + " AND ".join(t_cond)
    cur.execute(total_query, t_params)
    total = cur.fetchone()

    # Grafik BBM per kendaraan — query terpisah sesuai filter
    grafik_base = """
        SELECT k.No_Polisi, COALESCE(SUM(b.Jumlah_BBM),0) as total
        FROM pengisian_bbm b
        LEFT JOIN kendaraan k ON b.Id_Kendaraan = k.ID_Kendaraan
    """
    g_params = []
    g_cond = ["b.Status_Verifikasi = 'Terverifikasi'"]
    if bulan:
        g_cond.append("MONTH(b.Tanggal) = %s")
        g_params.append(bulan)
    if tahun:
        g_cond.append("YEAR(b.Tanggal) = %s")
        g_params.append(tahun)
    if g_cond:
        grafik_base += " WHERE " + " AND ".join(g_cond)
    grafik_base += " GROUP BY k.ID_Kendaraan, k.No_Polisi ORDER BY total DESC LIMIT 10"
    cur.execute(grafik_base, g_params)
    grafik_rows = cur.fetchall()
    grafik_label = json.dumps([r[0] for r in grafik_rows]) if grafik_rows else json.dumps([])
    grafik_data  = json.dumps([float(r[1]) for r in grafik_rows]) if grafik_rows else json.dumps([])

    cur.close()
    return render_template('laporan/bbm.html',
        data=data, stat_kendaraan=stat_kendaraan, total=total,
        grafik_label=grafik_label, grafik_data=grafik_data,
        bulan=bulan, tahun=tahun)


# =============================================
# LAPORAN MAINTENANCE
# =============================================
@laporan_bp.route('/laporan/maintenance')
def laporan_maintenance():
    if not admin_required():
        return redirect(url_for('auth.login'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()

    bulan = request.args.get('bulan', '')
    tahun = request.args.get('tahun', '')

    # Opsi 10-B: laporan hanya menampilkan data yang sudah Terverifikasi.
    # Helper membangun klausa WHERE (+ filter Bulan/Tahun) untuk alias tabel tertentu.
    def _filter(alias=''):
        conds = [f"{alias}Status_Verifikasi = 'Terverifikasi'"]
        p = []
        if bulan:
            conds.append(f"MONTH({alias}Tanggal) = %s"); p.append(bulan)
        if tahun:
            conds.append(f"YEAR({alias}Tanggal) = %s"); p.append(tahun)
        return " WHERE " + " AND ".join(conds), p

    # --- Tabel detail ---
    w, p = _filter('m.')
    cur.execute(f"""
        SELECT m.ID_Maintenance, m.Tanggal, d.Nama_Driver, k.No_Polisi, k.Merek, k.Tipe,
               m.KM_Kendaraan, m.Lokasi_Maintenance, m.Keluhan, m.Jumlah_Keluhan,
               m.Spareparts, m.Jumlah_Spareparts
        FROM maintenance m
        LEFT JOIN driver d ON m.ID_Driver = d.Id_Driver
        LEFT JOIN kendaraan k ON m.ID_Kendaraan = k.ID_Kendaraan
        {w} ORDER BY m.Tanggal DESC
    """, p)
    data = cur.fetchall()

    # --- Ringkasan total ---
    w, p = _filter('')
    cur.execute(f"""
        SELECT COUNT(*), COUNT(DISTINCT ID_Kendaraan),
               COALESCE(SUM(Jumlah_Keluhan),0), COALESCE(SUM(Jumlah_Spareparts),0)
        FROM maintenance {w}
    """, p)
    total = cur.fetchone()

    # --- Statistik per kendaraan (urut paling sering dirawat) ---
    w, p = _filter('m.')
    cur.execute(f"""
        SELECT k.No_Polisi, k.Merek, k.Tipe, COUNT(m.ID_Maintenance),
               COALESCE(SUM(m.Jumlah_Keluhan),0), COALESCE(SUM(m.Jumlah_Spareparts),0),
               MAX(m.Tanggal)
        FROM maintenance m
        LEFT JOIN kendaraan k ON m.ID_Kendaraan = k.ID_Kendaraan
        {w}
        GROUP BY k.ID_Kendaraan, k.No_Polisi, k.Merek, k.Tipe
        ORDER BY 4 DESC
    """, p)
    stat_kendaraan = cur.fetchall()

    # --- Grafik: 10 kendaraan paling sering dirawat ---
    w, p = _filter('m.')
    cur.execute(f"""
        SELECT k.No_Polisi, COUNT(m.ID_Maintenance) AS jml
        FROM maintenance m
        LEFT JOIN kendaraan k ON m.ID_Kendaraan = k.ID_Kendaraan
        {w}
        GROUP BY k.ID_Kendaraan, k.No_Polisi
        ORDER BY jml DESC LIMIT 10
    """, p)
    g = cur.fetchall()
    grafik_label = json.dumps([r[0] for r in g]) if g else json.dumps([])
    grafik_data  = json.dumps([int(r[1]) for r in g]) if g else json.dumps([])

    # --- Grafik: tren maintenance per bulan ---
    w, p = _filter('')
    cur.execute(f"""
        SELECT DATE_FORMAT(Tanggal, '%%b %%Y'), YEAR(Tanggal), MONTH(Tanggal), COUNT(*)
        FROM maintenance {w}
        GROUP BY YEAR(Tanggal), MONTH(Tanggal), DATE_FORMAT(Tanggal, '%%b %%Y')
        ORDER BY YEAR(Tanggal), MONTH(Tanggal) LIMIT 12
    """, p)
    t = cur.fetchall()
    tren_label = json.dumps([r[0] for r in t]) if t else json.dumps([])
    tren_data  = json.dumps([int(r[3]) for r in t]) if t else json.dumps([])

    cur.close()
    return render_template('laporan/maintenance.html',
        data=data, total=total, stat_kendaraan=stat_kendaraan,
        grafik_label=grafik_label, grafik_data=grafik_data,
        tren_label=tren_label, tren_data=tren_data,
        bulan=bulan, tahun=tahun)


# =============================================
# LAPORAN INSPEKSI
# =============================================
# 17 komponen kondisi (kolom DB, label tampilan).
KOMPONEN_INSPEKSI_LAP = [
    ('Oli_Mesin', 'Oli Mesin'),
    ('Oli_Transmisi_Gardan', 'Oli Transmisi & Gardan'),
    ('Air_Radiator', 'Air Radiator'),
    ('Minyak_Rem', 'Minyak Rem'),
    ('V_Belt', 'V-Belt'),
    ('Body_Exterior', 'Body & Exterior'),
    ('Ban', 'Ban'),
    ('Interior_Kelengkapan', 'Interior & Kelengkapan'),
    ('Lampu_Lampu', 'Lampu-lampu'),
    ('Suara_Mesin', 'Suara Mesin'),
    ('Getaran_Mesin', 'Getaran Mesin'),
    ('Indikator_Dashboard', 'Indikator Dashboard'),
    ('Asap_Knalpot', 'Asap Knalpot'),
    ('Transmisi', 'Transmisi'),
    ('Power_Steering', 'Power Steering'),
    ('Pengereman', 'Pengereman'),
    ('Suspensi_Kaki_Kaki', 'Suspensi & Kaki-kaki'),
]


@laporan_bp.route('/laporan/inspeksi')
def laporan_inspeksi():
    if not admin_required():
        return redirect(url_for('auth.login'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()

    bulan = request.args.get('bulan', '')
    tahun = request.args.get('tahun', '')

    def _filter(alias=''):
        conds = [f"{alias}Status_Verifikasi = 'Terverifikasi'"]
        p = []
        if bulan:
            conds.append(f"MONTH({alias}Tanggal) = %s"); p.append(bulan)
        if tahun:
            conds.append(f"YEAR({alias}Tanggal) = %s"); p.append(tahun)
        return " WHERE " + " AND ".join(conds), p

    # Ekspresi jumlah komponen 'Tidak Normal' per baris (dengan/ tanpa alias tabel).
    tn_i = " + ".join(f"(i.{c}='Tidak Normal')" for c, _ in KOMPONEN_INSPEKSI_LAP)
    tn_x = " + ".join(f"({c}='Tidak Normal')" for c, _ in KOMPONEN_INSPEKSI_LAP)
    sum_each = ", ".join(f"COALESCE(SUM({c}='Tidak Normal'),0)" for c, _ in KOMPONEN_INSPEKSI_LAP)

    # --- Tabel detail (+ jumlah temuan tidak normal per baris) ---
    w, p = _filter('i.')
    cur.execute(f"""
        SELECT i.ID_Inspeksi, i.Tanggal, d.Nama_Driver, k.No_Polisi, k.Merek, k.Tipe,
               i.KM_Kendaraan, ({tn_i}) AS jml_tn, i.Catatan
        FROM inspeksi i
        LEFT JOIN driver d ON i.ID_Driver = d.Id_Driver
        LEFT JOIN kendaraan k ON i.ID_Kendaraan = k.ID_Kendaraan
        {w} ORDER BY i.Tanggal DESC
    """, p)
    data = cur.fetchall()

    # --- Ringkasan total ---
    w, p = _filter('')
    cur.execute(f"""
        SELECT COUNT(*), COUNT(DISTINCT ID_Kendaraan), COALESCE(SUM({tn_x}),0)
        FROM inspeksi {w}
    """, p)
    total = cur.fetchone()
    total_insp = int(total[0]) if total else 0
    total_tn = int(total[2]) if total else 0
    pct_tn = round(total_tn / (total_insp * len(KOMPONEN_INSPEKSI_LAP)) * 100, 1) if total_insp else 0

    # --- Statistik per komponen (komponen paling sering bermasalah) ---
    w, p = _filter('')
    cur.execute(f"SELECT {sum_each} FROM inspeksi {w}", p)
    komp_row = cur.fetchone() or [0] * len(KOMPONEN_INSPEKSI_LAP)
    per_komponen = sorted(
        [{'label': lbl, 'jml': int(komp_row[i] or 0),
          'pct': round((komp_row[i] or 0) / total_insp * 100, 1) if total_insp else 0}
         for i, (c, lbl) in enumerate(KOMPONEN_INSPEKSI_LAP)],
        key=lambda x: x['jml'], reverse=True)
    komp_label = json.dumps([x['label'] for x in per_komponen])
    komp_data  = json.dumps([x['jml'] for x in per_komponen])

    # --- Statistik per kendaraan (urut temuan tidak normal terbanyak) ---
    w, p = _filter('i.')
    cur.execute(f"""
        SELECT k.No_Polisi, k.Merek, k.Tipe, COUNT(i.ID_Inspeksi),
               COALESCE(SUM({tn_i}),0), MAX(i.Tanggal)
        FROM inspeksi i
        LEFT JOIN kendaraan k ON i.ID_Kendaraan = k.ID_Kendaraan
        {w}
        GROUP BY k.ID_Kendaraan, k.No_Polisi, k.Merek, k.Tipe
        ORDER BY 5 DESC
    """, p)
    stat_kendaraan = cur.fetchall()

    # --- Grafik: 10 kendaraan dengan temuan tidak normal terbanyak ---
    top_k = stat_kendaraan[:10]
    gk_label = json.dumps([r[0] for r in top_k])
    gk_data  = json.dumps([int(r[4]) for r in top_k])

    cur.close()
    return render_template('laporan/inspeksi.html',
        data=data, total=total, total_tn=total_tn, pct_tn=pct_tn,
        per_komponen=per_komponen, stat_kendaraan=stat_kendaraan,
        komp_label=komp_label, komp_data=komp_data,
        gk_label=gk_label, gk_data=gk_data,
        bulan=bulan, tahun=tahun)