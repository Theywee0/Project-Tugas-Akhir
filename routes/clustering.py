from flask import Blueprint, render_template, request, redirect, url_for, session, flash, Response
import json
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import MinMaxScaler
from datetime import date
import io
import csv

clustering_bp = Blueprint('clustering', __name__)

def get_mysql():
    from app import mysql
    return mysql

def admin_required():
    if 'user_id' not in session or session.get('role') != 'kepala_operasional_gs':
        return False
    return True

# ================================================================
# HALAMAN UTAMA CLUSTERING
# ================================================================
@clustering_bp.route('/clustering', methods=['GET', 'POST'])
def index_clustering():
    if not admin_required():
        return redirect(url_for('auth.login'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()
    hasil = None
    error = None

    if request.method == 'POST':
        try:
            if True:
                # 1. AMBIL SEMUA KENDARAAN DENGAN SATU QUERY BESAR (MENGATASI N+1 PROBLEM)
                cur.execute("""
                    SELECT 
                        k.ID_Kendaraan, k.No_Polisi, k.Merek, k.Tipe, k.SKB,
                        COALESCE(p.Total_KM, 0) as total_jarak,
                        COALESCE(p.Frekuensi, 0) as frekuensi,
                        COALESCE(b.Total_BBM, 0) as total_bbm,
                        COALESCE(b.Jarak_Tercover, 0) as jarak_tercover,
                        COALESCE(m.Jml_Maintenance, 0) as jml_maintenance,
                        COALESCE(i.Jml_Inspeksi, 0) as jml_inspeksi_tn
                    FROM kendaraan k
                    LEFT JOIN (
                        SELECT ID_Kendaraan, SUM(Jumlah_KM) as Total_KM, COUNT(*) as Frekuensi 
                        FROM perjalanan WHERE Status_Verifikasi = 'Terverifikasi' GROUP BY ID_Kendaraan
                    ) p ON k.ID_Kendaraan = p.ID_Kendaraan
                    LEFT JOIN (
                        SELECT Id_Kendaraan, SUM(Jumlah_BBM) as Total_BBM, SUM(Jumlah_Km) as Jarak_Tercover 
                        FROM pengisian_bbm WHERE Status_Verifikasi = 'Terverifikasi' GROUP BY Id_Kendaraan
                    ) b ON k.ID_Kendaraan = b.Id_Kendaraan
                    LEFT JOIN (
                        SELECT ID_Kendaraan, COUNT(*) as Jml_Maintenance 
                        FROM maintenance WHERE Status_Verifikasi = 'Terverifikasi' GROUP BY ID_Kendaraan
                    ) m ON k.ID_Kendaraan = m.ID_Kendaraan
                    LEFT JOIN (
                        SELECT ID_Kendaraan, COUNT(*) as Jml_Inspeksi 
                        FROM inspeksi WHERE Status_Verifikasi = 'Terverifikasi' 
                        AND (Oli_Mesin = 'Tidak Normal' OR Oli_Transmisi_Gardan = 'Tidak Normal' OR Air_Radiator = 'Tidak Normal' OR Minyak_Rem = 'Tidak Normal' OR V_Belt = 'Tidak Normal' OR Body_Exterior = 'Tidak Normal' OR Ban = 'Tidak Normal' OR Interior_Kelengkapan = 'Tidak Normal' OR Lampu_Lampu = 'Tidak Normal' OR Suara_Mesin = 'Tidak Normal' OR Getaran_Mesin = 'Tidak Normal' OR Indikator_Dashboard = 'Tidak Normal' OR Asap_Knalpot = 'Tidak Normal' OR Transmisi = 'Tidak Normal' OR Power_Steering = 'Tidak Normal' OR Pengereman = 'Tidak Normal' OR Suspensi_Kaki_Kaki = 'Tidak Normal')
                        GROUP BY ID_Kendaraan
                    ) i ON k.ID_Kendaraan = i.ID_Kendaraan
                    ORDER BY k.ID_Kendaraan ASC
                """)
                kendaraan_rows = cur.fetchall()

                data = []
                for row in kendaraan_rows:
                    id_k, no_pol, merek, tipe, skb = row[0:5]
                    total_jarak, frekuensi, total_bbm, jarak_tercover, jml_maintenance, jml_inspeksi_tn = row[5:11]
                    
                    # Konversi tipe data
                    total_jarak = float(total_jarak)
                    frekuensi = int(frekuensi)
                    total_bbm = float(total_bbm)
                    jarak_tercover = float(jarak_tercover)
                    jml_maintenance = int(jml_maintenance)
                    jml_inspeksi_tn = int(jml_inspeksi_tn)

                    # Perhitungan rumus dilakukan murni di Python menggunakan memori
                    rasio_konsumsi = round(total_bbm / jarak_tercover, 4) if jarak_tercover > 0 else 0.0
                    standar = float(skb) if skb else 0.0
                    selisih = round(rasio_konsumsi - standar, 4)

                    data.append({
                        'id_kendaraan': id_k, 'no_polisi': no_pol, 'merek': merek, 'tipe': tipe,
                        'total_jarak': total_jarak, 'jarak_tercover_bbm': jarak_tercover,
                        'total_bbm': total_bbm, 'rasio_konsumsi': rasio_konsumsi,
                        'standar_konsumsibbm': standar, 'selisih_konsumsibbm': selisih,
                        'frekuensi_perjalanan': frekuensi, 'jumlah_maintenance': jml_maintenance,
                        'jumlah_inspeksi_tn': jml_inspeksi_tn,
                    })

                # -----------------------------------------------------------
                # FILTER: Kendaraan harus memiliki Jarak > 0 DAN BBM > 0
                # Alasan: Jika BBM = 0, maka rasio_konsumsi menjadi 0. 
                # Angka 0 ini BUKAN berarti kendaraan sangat irit, melainkan 
                # DATANYA BELUM ADA (Missing Data). Memasukkan rasio 0 
                # akan merusak skala MinMaxScaler (menjadi titik minimum palsu) 
                # dan membuat kendaraan normal lainnya bergeser ke "Kerusakan".
                # -----------------------------------------------------------
                data_valid = [d for d in data if d['total_jarak'] > 0 and d['total_bbm'] > 0]
                
                # Kendaraan yang belum punya data lengkap (Jarak 0 atau BBM 0)
                data_tanpa_operasional = [d for d in data if d['total_jarak'] == 0 or d['total_bbm'] == 0]

                if len(data_valid) < 2:
                    # =======================================================
                    # PENANGANAN JIKA DATA OPERASIONAL < 2 KENDARAAN
                    # =======================================================
                    semua_kendaraan = data_valid + data_tanpa_operasional
                    label_normal = 0
                    
                    for d in semua_kendaraan:
                        cur.execute("SELECT Id_Cluster FROM hasil_cluster WHERE Id_Kendaraan = %s", (d['id_kendaraan'],))
                        existing = cur.fetchone()
                        if existing:
                            cur.execute("""
                                UPDATE hasil_cluster SET
                                    Total_Jarak=%s, Total_Bbm=%s, Rasio_Konsumsi=%s,
                                    Standar_Konsumsibbm=%s, Selisih_Konsumsibbm=%s,
                                    Frekuensi_Perjalanan=%s, Jumlah_Maintenance=%s,
                                    Jumlah_Inspeksi_Tidak_Normal=%s, Cluster_Label=%s, Kategori='Normal'
                                WHERE Id_Cluster=%s
                            """, (d['total_jarak'], d['total_bbm'], d['rasio_konsumsi'], d['standar_konsumsibbm'], d['selisih_konsumsibbm'], d['frekuensi_perjalanan'], d['jumlah_maintenance'], d['jumlah_inspeksi_tn'], label_normal, existing[0]))
                        else:
                            cur.execute("""
                                INSERT INTO hasil_cluster (Id_Kendaraan, Total_Jarak, Total_Bbm, Rasio_Konsumsi, Standar_Konsumsibbm, Selisih_Konsumsibbm, Frekuensi_Perjalanan, Jumlah_Maintenance, Jumlah_Inspeksi_Tidak_Normal, Cluster_Label, Kategori)
                                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'Normal')
                            """, (d['id_kendaraan'], d['total_jarak'], d['total_bbm'], d['rasio_konsumsi'], d['standar_konsumsibbm'], d['selisih_konsumsibbm'], d['frekuensi_perjalanan'], d['jumlah_maintenance'], d['jumlah_inspeksi_tn'], label_normal))
                    
                    mysql.connection.commit()
                    
                    hasil_lengkap = []
                    for d in semua_kendaraan:
                        hasil_lengkap.append({**d, 'cluster_label': label_normal, 'kategori': 'Normal'})
                        
                    ringkasan = {
                        'Normal': len(semua_kendaraan),
                        'Kerusakan Ringan': 0,
                        'Kerusakan Berat': 0
                    }
                    
                    hasil = {
                        'sukses': True, 'pesan': f'Analisis berhasil. Mengingat data operasional yang terverifikasi belum mencukupi untuk komputasi K-Means, {len(semua_kendaraan)} kendaraan diatur ke kondisi awal (Normal).',
                        'iterasi': 0, 'inertia': 0.0,
                        'ringkasan': ringkasan, 'hasil_lengkap': hasil_lengkap, 
                        'n_kendaraan': len(semua_kendaraan), 'elbow_k': [], 'elbow_wcss': [], 'jumlah_k': 1
                    }
                    # flash(hasil['pesan'], 'success')
                else:
                    X = np.array([
                        [
                            d['total_jarak'],          # Jarak memengaruhi umur pakai komponen
                            d['rasio_konsumsi'],       # Indikator efisiensi pembakaran (cukup rasio saja, tidak usah total_bbm)
                            d['frekuensi_perjalanan'], # Menandakan tingkat stress pemakaian
                            d['jumlah_maintenance'],   # Indikator sering masuk bengkel
                            d['jumlah_inspeksi_tn']    # Indikator keluhan harian driver
                        ] for d in data_valid
                    ])

                    scaler = MinMaxScaler()
                    X_scaled = scaler.fit_transform(X)

                    # =======================================================
                    # FEATURE WEIGHTING (PEMBOBOTAN FITUR)
                    # Fokus: Mengutamakan fitur indikasi kerusakan kendaraan
                    # =======================================================
                    weight_jarak = 1.0      # Diturunkan (Fitur Operasional)
                    weight_rasio = 1.0      # Diturunkan (Fitur Operasional)
                    weight_frek = 0.5       # Standar (Stres Pemakaian)
                    weight_maint = 2.0      # SANGAT TINGGI (Kerusakan Utama)
                    weight_inspeksi = 3.0   # SANGAT TINGGI (Keluhan Utama)
                    
                    # Mengalikan hasil scaling (MinMax) dengan bobot
                    # Urutan kolom X: [0]Jarak, [1]Rasio, [2]Frekuensi, [3]Maintenance, [4]Inspeksi
                    X_scaled[:, 0] *= weight_jarak
                    X_scaled[:, 1] *= weight_rasio
                    X_scaled[:, 2] *= weight_frek
                    X_scaled[:, 3] *= weight_maint
                    X_scaled[:, 4] *= weight_inspeksi
                    # =======================================================

                    elbow_k, elbow_wcss = [], []
                    k_max = min(6, len(data_valid))
                    for kk in range(1, k_max + 1):
                        km_tmp = KMeans(n_clusters=kk, random_state=42, n_init=10)
                        km_tmp.fit(X_scaled)
                        elbow_k.append(kk)
                        elbow_wcss.append(round(float(km_tmp.inertia_), 4))

                    # -------------------------------------------------------------
                    # JALANKAN K-MEANS UTAMA DENGAN K DIKUNCI PERMANEN = 3
                    # -------------------------------------------------------------
                    # Menggunakan perlindungan min() jika jumlah kendaraan kebetulan < 3
                    jumlah_k = min(3, len(data_valid))
                    
                    kmeans = KMeans(n_clusters=jumlah_k, random_state=42, n_init=10)
                    labels = kmeans.fit_predict(X_scaled)

                    # -------------------------------------------------------------
                    # PELABELAN OTOMATIS & DINAMIS BERDASARKAN CENTROID
                    # -------------------------------------------------------------
                    centroids = kmeans.cluster_centers_
                    
                    skor_kerusakan = {}
                    for cl in range(jumlah_k):
                        skor_kerusakan[cl] = float(sum(centroids[cl]))
                    
                    urutan = sorted(skor_kerusakan, key=skor_kerusakan.get)
                    
                    if jumlah_k == 1:
                        LABEL_KATEGORI = ['Normal']
                    elif jumlah_k == 2:
                        LABEL_KATEGORI = ['Normal', 'Kerusakan Berat']
                    else:
                        LABEL_KATEGORI = ['Normal', 'Kerusakan Ringan', 'Kerusakan Berat']
                        
                    mapping_label = {}
                    for idx, cl in enumerate(urutan):
                        if idx < len(LABEL_KATEGORI):
                            mapping_label[cl] = LABEL_KATEGORI[idx]
                        else:
                            mapping_label[cl] = f'Cluster {cl}'
                    
                    for i, d in enumerate(data_valid):
                        label_angka = int(labels[i])
                        kategori_sementara = mapping_label[label_angka]

                        cur.execute("SELECT Id_Cluster FROM hasil_cluster WHERE Id_Kendaraan = %s", (d['id_kendaraan'],))
                        existing = cur.fetchone()

                        if existing:
                            cur.execute("""
                                UPDATE hasil_cluster SET
                                    Total_Jarak=%s, Total_Bbm=%s, Rasio_Konsumsi=%s,
                                    Standar_Konsumsibbm=%s, Selisih_Konsumsibbm=%s,
                                    Frekuensi_Perjalanan=%s, Jumlah_Maintenance=%s,
                                    Jumlah_Inspeksi_Tidak_Normal=%s, Cluster_Label=%s, Kategori=%s
                                WHERE Id_Cluster=%s
                            """, (d['total_jarak'], d['total_bbm'], d['rasio_konsumsi'], d['standar_konsumsibbm'], d['selisih_konsumsibbm'], d['frekuensi_perjalanan'], d['jumlah_maintenance'], d['jumlah_inspeksi_tn'], label_angka, kategori_sementara, existing[0]))
                        else:
                            cur.execute("""
                                INSERT INTO hasil_cluster (Id_Kendaraan, Total_Jarak, Total_Bbm, Rasio_Konsumsi, Standar_Konsumsibbm, Selisih_Konsumsibbm, Frekuensi_Perjalanan, Jumlah_Maintenance, Jumlah_Inspeksi_Tidak_Normal, Cluster_Label, Kategori)
                                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            """, (d['id_kendaraan'], d['total_jarak'], d['total_bbm'], d['rasio_konsumsi'], d['standar_konsumsibbm'], d['selisih_konsumsibbm'], d['frekuensi_perjalanan'], d['jumlah_maintenance'], d['jumlah_inspeksi_tn'], label_angka, kategori_sementara))

                    mysql.connection.commit()

                    # -----------------------------------------------------------
                    # KENDARAAN TANPA DATA OPERASIONAL → LANGSUNG MASUK "Normal"
                    # Logika: skor kerusakan = 0 di semua fitur → Normal.
                    # Tidak perlu K-Means untuk menentukan ini.
                    # Tetap dikeluarkan dari perhitungan agar tidak mengacaukan
                    # skala MinMaxScaler untuk kendaraan lain.
                    # -----------------------------------------------------------
                    # Cari label angka cluster Normal dari mapping
                    label_normal = [k for k, v in mapping_label.items() if v == 'Normal'][0]

                    for d in data_tanpa_operasional:
                        cur.execute("SELECT Id_Cluster FROM hasil_cluster WHERE Id_Kendaraan = %s", (d['id_kendaraan'],))
                        existing = cur.fetchone()
                        if existing:
                            cur.execute("""
                                UPDATE hasil_cluster SET
                                    Total_Jarak=0, Total_Bbm=0, Rasio_Konsumsi=0,
                                    Standar_Konsumsibbm=%s, Selisih_Konsumsibbm=0,
                                    Frekuensi_Perjalanan=0, Jumlah_Maintenance=0,
                                    Jumlah_Inspeksi_Tidak_Normal=0, Cluster_Label=%s, Kategori='Normal'
                                WHERE Id_Cluster=%s
                            """, (d['standar_konsumsibbm'], label_normal, existing[0]))
                        else:
                            cur.execute("""
                                INSERT INTO hasil_cluster (Id_Kendaraan, Total_Jarak, Total_Bbm, Rasio_Konsumsi, Standar_Konsumsibbm, Selisih_Konsumsibbm, Frekuensi_Perjalanan, Jumlah_Maintenance, Jumlah_Inspeksi_Tidak_Normal, Cluster_Label, Kategori)
                                VALUES (%s, 0, 0, 0, %s, 0, 0, 0, 0, %s, 'Normal')
                            """, (d['id_kendaraan'], d['standar_konsumsibbm'], label_normal))
                    mysql.connection.commit()

                    hasil_lengkap = []
                    ringkasan = {}
                    for i, d in enumerate(data_valid):
                        kat = mapping_label[int(labels[i])]
                        ringkasan[kat] = ringkasan.get(kat, 0) + 1
                        hasil_lengkap.append({**d, 'cluster_label': int(labels[i]), 'kategori': kat})

                    # Kendaraan tanpa data masuk ke ringkasan & hasil sebagai Normal
                    if data_tanpa_operasional:
                        ringkasan['Normal'] = ringkasan.get('Normal', 0) + len(data_tanpa_operasional)
                        for d in data_tanpa_operasional:
                            hasil_lengkap.append({**d, 'cluster_label': label_normal, 'kategori': 'Normal'})

                    hasil = {
                        'sukses': True, 'pesan': f'Clustering selesai! Membentuk {jumlah_k} kelompok.',
                        'iterasi': kmeans.n_iter_, 'inertia': round(kmeans.inertia_, 4),
                        'ringkasan': ringkasan, 'hasil_lengkap': hasil_lengkap, 
                        'n_kendaraan': len(data_valid) + len(data_tanpa_operasional), 'elbow_k': elbow_k, 'elbow_wcss': elbow_wcss, 'jumlah_k': jumlah_k
                    }
                    flash(hasil['pesan'], 'success')
        except Exception as e:
            mysql.connection.rollback()
            error = f'Terjadi kesalahan: {str(e)}'

    cur.execute("""
        SELECT hc.Id_Cluster, k.No_Polisi, k.Merek, k.Tipe, hc.Total_Jarak, hc.Total_Bbm, hc.Rasio_Konsumsi, hc.Selisih_Konsumsibbm, hc.Frekuensi_Perjalanan, hc.Jumlah_Maintenance, hc.Jumlah_Inspeksi_Tidak_Normal, hc.Cluster_Label, hc.Kategori
        FROM hasil_cluster hc
        LEFT JOIN kendaraan k ON hc.Id_Kendaraan = k.ID_Kendaraan
        ORDER BY hc.Cluster_Label
    """)
    riwayat = cur.fetchall()
    
    profil_cluster = {
        'Normal': {'count': 0, 'jarak': 0, 'bbm': 0, 'rasio': 0, 'maint': 0, 'inspeksi': 0, 'label_asli': '-'},
        'Kerusakan Ringan': {'count': 0, 'jarak': 0, 'bbm': 0, 'rasio': 0, 'maint': 0, 'inspeksi': 0, 'label_asli': '-'},
        'Kerusakan Berat': {'count': 0, 'jarak': 0, 'bbm': 0, 'rasio': 0, 'maint': 0, 'inspeksi': 0, 'label_asli': '-'}
    }
    for r in riwayat:
        kat = r[12]
        if kat not in profil_cluster:
            profil_cluster[kat] = {'count': 0, 'jarak': 0, 'bbm': 0, 'rasio': 0, 'maint': 0, 'inspeksi': 0, 'label_asli': r[11]}
        profil_cluster[kat]['count'] += 1
        profil_cluster[kat]['jarak'] += r[4]
        profil_cluster[kat]['bbm'] += r[5]
        profil_cluster[kat]['rasio'] += r[6]
        profil_cluster[kat]['maint'] += r[9]
        profil_cluster[kat]['inspeksi'] += r[10]
        profil_cluster[kat]['label_asli'] = r[11]

    for k, v in profil_cluster.items():
        if v['count'] > 0:
            v['avg_jarak'] = round(v['jarak'] / v['count'], 1)
            v['avg_bbm'] = round(v['bbm'] / v['count'], 1)
            v['rasio'] = round(v['rasio'] / v['count'], 4)
            v['maint'] = round(v['maint'] / v['count'], 1)
            v['inspeksi'] = round(v['inspeksi'] / v['count'], 1)
        else:
            v['avg_jarak'] = 0
            v['avg_bbm'] = 0
            v['rasio'] = 0
            v['maint'] = 0
            v['inspeksi'] = 0

    scatter_data = {}
    for r in riwayat:
        kat = r[12] if r[12] else 'Belum Dianalisis'
        scatter_data.setdefault(kat, []).append({'x': float(r[4]) if r[4] else 0, 'y': float(r[5]) if r[5] else 0, 'label': r[1] if r[1] else '-'})

    cur.close()
    return render_template('clustering/index.html', hasil=hasil, error=error, riwayat=riwayat, scatter_data=json.dumps(scatter_data), profil_cluster=profil_cluster)


# ================================================================
# EXPORT DATA MENTAH KE CSV UNTUK RAPIDMINER
# ================================================================
@clustering_bp.route('/clustering/export_csv')
def export_csv():
    if not admin_required():
        return redirect(url_for('auth.login'))

    mysql = get_mysql()
    cur = mysql.connection.cursor()

    # Ambil data dari hasil_cluster tapi HANYA fitur numeriknya saja (plus ID)
    cur.execute("""
        SELECT Id_Kendaraan, Total_Jarak, Total_Bbm, Rasio_Konsumsi, 
               Standar_Konsumsibbm, Selisih_Konsumsibbm, Frekuensi_Perjalanan, 
               Jumlah_Maintenance, Jumlah_Inspeksi_Tidak_Normal
        FROM hasil_cluster
        ORDER BY Id_Kendaraan
    """)
    rows = cur.fetchall()
    cur.close()

    # Menulis ke memori menggunakan io.StringIO
    output = io.StringIO()
    writer = csv.writer(output, delimiter=',')
    
    # Tulis header kolom
    writer.writerow([
        'Id_Kendaraan', 'Total_Jarak', 'Total_Bbm', 'Rasio_Konsumsi', 
        'Standar_Konsumsibbm', 'Selisih_Konsumsibbm', 'Frekuensi_Perjalanan', 
        'Jumlah_Maintenance', 'Jumlah_Inspeksi_Tidak_Normal'
    ])
    
    # Tulis data baris per baris
    for row in rows:
        writer.writerow(row)

    # Buat response HTTP untuk mengunduh file
    csv_data = output.getvalue()
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=dataset_mentah_kendaraan.csv"}
    )