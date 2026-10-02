def get_user_by_username(mysql, username):
    cur = mysql.connection.cursor()
    cur.execute("SELECT Id_User, Nama, Username, Password, Role FROM user WHERE Username = %s", (username,))
    user = cur.fetchone()
    cur.close()
    return user

def update_password(mysql, id_user, hashed_password):
    cur = mysql.connection.cursor()
    cur.execute("UPDATE user SET Password=%s WHERE Id_User=%s", (hashed_password, id_user))
    mysql.connection.commit()
    cur.close()

def get_driver_id_by_user(mysql, user_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT Id_Driver FROM driver WHERE Id_User = %s", (user_id,))
    row = cur.fetchone()
    cur.close()
    return row[0] if row else None

def get_dashboard_driver_stats(mysql, id_driver, cond):
    cur = mysql.connection.cursor()
    stats = {'perjalanan': 0, 'bbm': 0.0, 'total_jarak': 0.0}
    
    cur.execute(f"SELECT COUNT(*) FROM perjalanan WHERE ID_Driver = %s AND {cond}", (id_driver,))
    stats['perjalanan'] = int(cur.fetchone()[0])
    
    cur.execute(f"SELECT COALESCE(SUM(Jumlah_BBM), 0) FROM pengisian_bbm WHERE Id_Driver = %s AND {cond}", (id_driver,))
    stats['bbm'] = float(cur.fetchone()[0])
    
    cur.execute(f"SELECT COALESCE(SUM(Jumlah_KM), 0) FROM perjalanan WHERE ID_Driver = %s AND {cond}", (id_driver,))
    stats['total_jarak'] = float(cur.fetchone()[0])
    
    cur.close()
    return stats

def get_dashboard_driver_pending(mysql, id_driver):
    cur = mysql.connection.cursor()
    pending = {'perjalanan': 0, 'bbm': 0, 'maintenance': 0, 'inspeksi': 0, 'total': 0}
    for key, tabel, kol in [('perjalanan', 'perjalanan', 'ID_Driver'),
                            ('bbm', 'pengisian_bbm', 'Id_Driver'),
                            ('maintenance', 'maintenance', 'ID_Driver'),
                            ('inspeksi', 'inspeksi', 'ID_Driver')]:
        cur.execute(f"SELECT COUNT(*) FROM {tabel} WHERE {kol} = %s AND Status_Verifikasi = 'Belum'", (id_driver,))
        pending[key] = int(cur.fetchone()[0])
    pending['total'] = sum(pending.values())
    cur.close()
    return pending

def get_dashboard_driver_aktivitas(mysql, id_driver):
    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT akt.tgl, akt.jenis, akt.nopol, akt.status FROM (
            SELECT p.Tanggal AS tgl, p.Jam AS jam, 'Perjalanan' AS jenis,
                   k.No_Polisi AS nopol, p.Status_Verifikasi AS status
            FROM perjalanan p LEFT JOIN kendaraan k ON p.ID_Kendaraan = k.ID_Kendaraan
            WHERE p.ID_Driver = %s
            UNION ALL
            SELECT b.Tanggal, b.Jam, 'Pengisian BBM', k.No_Polisi, b.Status_Verifikasi
            FROM pengisian_bbm b LEFT JOIN kendaraan k ON b.Id_Kendaraan = k.ID_Kendaraan
            WHERE b.Id_Driver = %s
            UNION ALL
            SELECT m.Tanggal, NULL, 'Maintenance', k.No_Polisi, m.Status_Verifikasi
            FROM maintenance m LEFT JOIN kendaraan k ON m.ID_Kendaraan = k.ID_Kendaraan
            WHERE m.ID_Driver = %s
            UNION ALL
            SELECT i.Tanggal, NULL, 'Inspeksi', k.No_Polisi, i.Status_Verifikasi
            FROM inspeksi i LEFT JOIN kendaraan k ON i.ID_Kendaraan = k.ID_Kendaraan
            WHERE i.ID_Driver = %s
        ) akt
        ORDER BY akt.tgl DESC, akt.jam DESC
        LIMIT 5
    """, (id_driver, id_driver, id_driver, id_driver))
    aktivitas = cur.fetchall()
    cur.close()
    return aktivitas
