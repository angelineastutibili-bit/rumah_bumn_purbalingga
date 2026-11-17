from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from datetime import datetime
from django.contrib.auth.models import User
from .models import UMKM, Produk, Stok, Chanel, StokChanel, Distribusi, RiwayatStok, BarangMasuk, BarangKeluar
from .forms import UMKMForm


class UMKMFeatureTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='admin_test', password='password123')
        self.client = Client()
        self.client.login(username='admin_test', password='password123')

    def test_umkm_form_default_timestamp(self):
        # Saat form UMKM dibuat tanpa mengisi tanggal_terdaftar, form tetap valid dan tanggal_terdaftar terisi otomatis
        form_data = {
            'nama': 'UMKM Keripik Tempe Enak',
            'pemilik': 'Pak Budi',
            'jenis_usaha': 'Kuliner',
            'alamat': 'Purbalingga Kulon',
            'kontak': '08123456789',
            'tanggal_terdaftar': '',
        }
        form = UMKMForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)
        umkm = form.save()
        self.assertIsNotNone(umkm.tanggal_terdaftar)

    def test_umkm_form_manual_histori_date(self):
        # Administrator dapat menginput tanggal terdaftar histori/manual secara spesifik
        manual_dt = datetime(2023, 5, 12, 10, 30)
        form_data = {
            'nama': 'UMKM Ukir Kayu Antik',
            'pemilik': 'Pak Bambang',
            'jenis_usaha': 'Kerajinan',
            'alamat': 'Bobotsari',
            'kontak': '08987654321',
            'tanggal_terdaftar': '2023-05-12T10:30',
        }
        form = UMKMForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)
        umkm = form.save()
        self.assertEqual(umkm.tanggal_terdaftar.year, 2023)
        self.assertEqual(umkm.tanggal_terdaftar.month, 5)
        self.assertEqual(umkm.tanggal_terdaftar.day, 12)

    def test_data_umkm_view_displays_tanggal_terdaftar(self):
        # Halaman tabel data UMKM menampilkan kolom dan tanggal terdaftar
        umkm = UMKM.objects.create(
            nama='Batik Cantik Purbalingga',
            jenis_usaha='Fashion',
            tanggal_terdaftar=timezone.now()
        )
        response = self.client.get(reverse('data_umkm'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Tanggal Terdaftar')
        self.assertContains(response, 'Batik Cantik Purbalingga')


class StokKantorSearchTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='admin_test', password='password123')
        self.client = Client()
        self.client.login(username='admin_test', password='password123')

        self.umkm = UMKM.objects.create(nama='UMKM Sejahtera', jenis_usaha='Makanan')
        self.produk1 = Produk.objects.create(
            kode_produk='PRD-SNK-001',
            nama_produk='Keripik Singkong Renyah',
            kategori='Snack Ringan',
            umkm=self.umkm
        )
        self.stok1, _ = Stok.objects.get_or_create(produk=self.produk1, defaults={'stok_kantor': 25})

        self.produk2 = Produk.objects.create(
            kode_produk='PRD-BVR-002',
            nama_produk='Sirup Jahe Wangi',
            kategori='Minuman Herbal',
            umkm=self.umkm
        )
        self.stok2, _ = Stok.objects.get_or_create(produk=self.produk2, defaults={'stok_kantor': 10})

    def test_search_by_nama_produk(self):
        # Pencarian berdasarkan Nama Produk
        response = self.client.get(reverse('data_stok'), {'q': 'Keripik'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Keripik Singkong Renyah')
        self.assertNotContains(response, 'Sirup Jahe Wangi')

    def test_search_by_kode_sku(self):
        # Pencarian berdasarkan Kode / SKU
        response = self.client.get(reverse('data_stok'), {'q': 'PRD-BVR-002'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sirup Jahe Wangi')
        self.assertNotContains(response, 'Keripik Singkong Renyah')

    def test_search_by_kategori(self):
        # Pencarian berdasarkan Kategori di menu Stok Kantor
        response = self.client.get(reverse('data_stok'), {'q': 'Minuman Herbal'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sirup Jahe Wangi')
        self.assertNotContains(response, 'Keripik Singkong Renyah')


class ChanelStokAlurTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='admin_test', password='password123')
        self.client = Client()
        self.client.login(username='admin_test', password='password123')

        self.umkm = UMKM.objects.create(nama='UMKM Purbalingga Hebat', jenis_usaha='Kuliner')
        self.produk = Produk.objects.create(
            kode_produk='PRD-KLP-001',
            nama_produk='Gula Kelapa Kristal',
            kategori='Pemanis Alami',
            umkm=self.umkm
        )
        self.stok, _ = Stok.objects.get_or_create(produk=self.produk, defaults={'stok_kantor': 50})
        self.chanel = Chanel.objects.create(nama_toko='Toko Oleh-Oleh Purbalingga', lokasi='Jl. Jendral Sudirman')

    def test_tambah_stok_dari_kantor_memotong_stok_kantor(self):
        # Alokasi 20 unit dari Stok Kantor ke Toko
        post_data = {
            'produk': self.produk.id,
            'jumlah': 20,
            'sumber_barang': 'kantor',
            'keterangan': 'Pengiriman alokasi display toko'
        }
        response = self.client.post(reverse('tambah_stok_chanel', args=[self.chanel.id]), post_data, follow=True)
        self.assertEqual(response.status_code, 200)

        # 1. Stok kantor harus otomatis berkurang dari 50 menjadi 30
        self.stok.refresh_from_db()
        self.assertEqual(self.stok.stok_kantor, 30)

        # 2. Stok toko harus bertambah menjadi 20
        stok_c = StokChanel.objects.get(produk=self.produk, chanel=self.chanel)
        self.assertEqual(stok_c.jumlah, 20)

        # 3. Harus tercatat di tabel Distribusi
        self.assertTrue(Distribusi.objects.filter(produk=self.produk, chanel=self.chanel, jumlah=20).exists())

        # 4. Riwayat stok kantor dan toko tercatat
        self.assertTrue(RiwayatStok.objects.filter(produk=self.produk, lokasi='Kantor', jenis_transaksi='DISTRIBUSI', jumlah=-20).exists())
        self.assertTrue(RiwayatStok.objects.filter(produk=self.produk, lokasi__icontains=self.chanel.nama_toko, jumlah=20).exists())

    def test_tambah_stok_melebihi_stok_kantor_ditolak(self):
        # Upaya mengalokasikan 60 unit sementara stok kantor hanya 50
        post_data = {
            'produk': self.produk.id,
            'jumlah': 60,
            'sumber_barang': 'kantor',
            'keterangan': 'Alokasi melebihi stok'
        }
        response = self.client.post(reverse('tambah_stok_chanel', args=[self.chanel.id]), post_data, follow=True)
        self.assertEqual(response.status_code, 200)

        # Transaksi harus ditolak, stok kantor tetap 50
        self.stok.refresh_from_db()
        self.assertEqual(self.stok.stok_kantor, 50)

        # Tidak ada penambahan stok di toko
        self.assertFalse(StokChanel.objects.filter(produk=self.produk, chanel=self.chanel).exists())
        self.assertContains(response, 'tidak mencukupi')

    def test_tambah_stok_sumber_langsung_tidak_memotong_kantor(self):
        # Penambahan dari sumber non-kantor (langsung)
        post_data = {
            'produk': self.produk.id,
            'jumlah': 15,
            'sumber_barang': 'langsung',
            'keterangan': 'Drop barang langsung dari pengrajin'
        }
        response = self.client.post(reverse('tambah_stok_chanel', args=[self.chanel.id]), post_data, follow=True)
        self.assertEqual(response.status_code, 200)

        # Stok kantor tetap 50
        self.stok.refresh_from_db()
        self.assertEqual(self.stok.stok_kantor, 50)

        # Stok toko bertambah 15
        stok_c = StokChanel.objects.get(produk=self.produk, chanel=self.chanel)
        self.assertEqual(stok_c.jumlah, 15)


class DistribusiMultiLokasiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='admin_test', password='password123')
        self.client = Client()
        self.client.login(username='admin_test', password='password123')

        self.umkm = UMKM.objects.create(nama='UMKM Kopi Purbalingga', jenis_usaha='Minuman')
        self.produk = Produk.objects.create(
            kode_produk='PRD-KPI-001',
            nama_produk='Kopi Robusta Gunung Slamet',
            kategori='Kopi',
            umkm=self.umkm
        )
        self.stok, _ = Stok.objects.get_or_create(produk=self.produk, defaults={'stok_kantor': 40})
        self.toko_a = Chanel.objects.create(nama_toko='Toko A Sentra UMKM', lokasi='Bobotsari')
        self.toko_b = Chanel.objects.create(nama_toko='Toko B Alun-Alun', lokasi='Purbalingga Kota')

    def test_distribusi_kantor_ke_toko_berhasil(self):
        # Distribusi 15 unit dari Kantor -> Toko A
        post_data = {
            'produk': self.produk.id,
            'asal': 'Kantor',
            'tujuan': f'chanel_{self.toko_a.id}',
            'jumlah': 15,
            'keterangan': 'Distribusi perdana ke Toko A'
        }
        response = self.client.post(reverse('tambah_distribusi'), post_data, follow=True)
        self.assertEqual(response.status_code, 200)

        # 1. Pengurangan di lokasi Asal (Kantor berkurang 40 - 15 = 25)
        self.stok.refresh_from_db()
        self.assertEqual(self.stok.stok_kantor, 25)

        # 2. Penambahan di lokasi Tujuan (Toko A bertambah 15, buat record baru jika belum ada)
        stok_toko_a = StokChanel.objects.get(produk=self.produk, chanel=self.toko_a)
        self.assertEqual(stok_toko_a.jumlah, 15)

        # 3. Record Distribusi tercatat dengan asal 'Kantor' dan tujuan nama toko
        self.assertTrue(Distribusi.objects.filter(
            produk=self.produk, asal='Kantor', tujuan=self.toko_a.nama_toko, jumlah=15
        ).exists())

    def test_distribusi_kantor_stok_tidak_mencukupi_ditolak(self):
        # Distribusi 50 unit dari Kantor (tersedia hanya 40)
        post_data = {
            'produk': self.produk.id,
            'asal': 'Kantor',
            'tujuan': f'chanel_{self.toko_a.id}',
            'jumlah': 50,
            'keterangan': 'Melebihi stok kantor'
        }
        response = self.client.post(reverse('tambah_distribusi'), post_data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'tidak mencukupi')

        # Stok kantor tidak berkurang, stok toko tidak terbuat
        self.stok.refresh_from_db()
        self.assertEqual(self.stok.stok_kantor, 40)
        self.assertFalse(StokChanel.objects.filter(produk=self.produk, chanel=self.toko_a).exists())

    def test_distribusi_antar_toko_berhasil(self):
        # Beri stok awal pada Toko A sebanyak 20 unit
        StokChanel.objects.create(produk=self.produk, chanel=self.toko_a, jumlah=20)

        # Mutasi 8 unit dari Toko A -> Toko B
        post_data = {
            'produk': self.produk.id,
            'asal': f'chanel_{self.toko_a.id}',
            'tujuan': f'chanel_{self.toko_b.id}',
            'jumlah': 8,
            'keterangan': 'Transfer stok antar toko'
        }
        response = self.client.post(reverse('tambah_distribusi'), post_data, follow=True)
        self.assertEqual(response.status_code, 200)

        # Toko A berkurang dari 20 menjadi 12
        stok_a = StokChanel.objects.get(produk=self.produk, chanel=self.toko_a)
        self.assertEqual(stok_a.jumlah, 12)

        # Toko B bertambah 8
        stok_b = StokChanel.objects.get(produk=self.produk, chanel=self.toko_b)
        self.assertEqual(stok_b.jumlah, 8)

        # Stok kantor tidak tersentuh
        self.stok.refresh_from_db()
        self.assertEqual(self.stok.stok_kantor, 40)

    def test_distribusi_antar_toko_stok_kurang_ditolak(self):
        # Toko A punya 5 unit
        StokChanel.objects.create(produk=self.produk, chanel=self.toko_a, jumlah=5)

        # Coba transfer 10 unit dari Toko A ke Toko B
        post_data = {
            'produk': self.produk.id,
            'asal': f'chanel_{self.toko_a.id}',
            'tujuan': f'chanel_{self.toko_b.id}',
            'jumlah': 10,
        }
        response = self.client.post(reverse('tambah_distribusi'), post_data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'tidak mencukupi')

        # Stok Toko A tetap 5, Toko B tidak terbuat
        stok_a = StokChanel.objects.get(produk=self.produk, chanel=self.toko_a)
        self.assertEqual(stok_a.jumlah, 5)
        self.assertFalse(StokChanel.objects.filter(produk=self.produk, chanel=self.toko_b).exists())

    def test_distribusi_toko_ke_kantor_retur(self):
        # Toko A punya 15 unit
        StokChanel.objects.create(produk=self.produk, chanel=self.toko_a, jumlah=15)

        # Retur 5 unit dari Toko A kembali ke Kantor
        post_data = {
            'produk': self.produk.id,
            'asal': f'chanel_{self.toko_a.id}',
            'tujuan': 'Kantor',
            'jumlah': 5,
            'keterangan': 'Retur kelebihan barang'
        }
        response = self.client.post(reverse('tambah_distribusi'), post_data, follow=True)
        self.assertEqual(response.status_code, 200)

        # Toko A berkurang 15 - 5 = 10
        stok_a = StokChanel.objects.get(produk=self.produk, chanel=self.toko_a)
        self.assertEqual(stok_a.jumlah, 10)

        # Kantor bertambah 40 + 5 = 45
        self.stok.refresh_from_db()
        self.assertEqual(self.stok.stok_kantor, 45)

    def test_distribusi_asal_dan_tujuan_sama_ditolak(self):
        post_data = {
            'produk': self.produk.id,
            'asal': 'Kantor',
            'tujuan': 'Kantor',
            'jumlah': 5,
        }
        response = self.client.post(reverse('tambah_distribusi'), post_data, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'tidak boleh sama')


class LaporanInventoriTests(TestCase):
    def setUp(self):
        from .models import BarangMasuk, BarangKeluar
        self.user = User.objects.create_user(username='admin_test', password='password123')
        self.client = Client()
        self.client.login(username='admin_test', password='password123')

        self.umkm = UMKM.objects.create(nama='UMKM Purbalingga Maju', jenis_usaha='Makanan')
        self.produk1 = Produk.objects.create(
            kode_produk='PRD-001',
            nama_produk='Kripik Nangka Super',
            kategori='Makanan Ringan',
            stok_minimum=10,
            umkm=self.umkm
        )
        self.stok1, _ = Stok.objects.get_or_create(produk=self.produk1, defaults={'stok_kantor': 5}) # menipis

        self.produk2 = Produk.objects.create(
            kode_produk='PRD-002',
            nama_produk='Sambal Knalpot Khas',
            kategori='Bumbu & Sambal',
            stok_minimum=5,
            umkm=self.umkm
        )
        self.stok2, _ = Stok.objects.get_or_create(produk=self.produk2, defaults={'stok_kantor': 20}) # aman

        self.chanel = Chanel.objects.create(nama_toko='Toko Wisata Purbalingga')
        StokChanel.objects.create(produk=self.produk1, chanel=self.chanel, jumlah=3)

        # Transaksi contoh
        BarangMasuk.objects.create(produk=self.produk1, jumlah=15, asal='Supplier A', keterangan='Restock awal')
        BarangKeluar.objects.create(produk=self.produk1, jumlah=5, tujuan='Konsumen Toko', keterangan='Penjualan')
        Distribusi.objects.create(produk=self.produk1, chanel=self.chanel, jumlah=3, asal='Kantor', tujuan=self.chanel.nama_toko, keterangan='Drop display')

    def test_laporan_stok_saat_ini(self):
        response = self.client.get(reverse('laporan'), {'jenis_laporan': 'stok_saat_ini', 'show_report': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Kripik Nangka Super')
        self.assertContains(response, 'Sambal Knalpot Khas')
        self.assertContains(response, 'Laporan Stok Saat Ini')

    def test_laporan_filter_produk_spesifik(self):
        # Saat produk 1 dipilih, hanya data produk 1 yang masuk ke dalam rows laporan
        response = self.client.get(reverse('laporan'), {
            'jenis_laporan': 'stok_saat_ini',
            'produk_id': self.produk1.id,
            'show_report': '1'
        })
        self.assertEqual(response.status_code, 200)
        rows = response.context['laporan_data']['rows']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['kode_produk'], self.produk1.kode_produk)
        self.assertEqual(rows[0]['nama_produk'], self.produk1.nama_produk)

    def test_laporan_barang_masuk(self):
        response = self.client.get(reverse('laporan'), {'jenis_laporan': 'barang_masuk', 'show_report': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Restock awal')
        self.assertContains(response, 'Supplier A')

    def test_laporan_barang_keluar(self):
        response = self.client.get(reverse('laporan'), {'jenis_laporan': 'barang_keluar', 'show_report': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Konsumen Toko')

    def test_laporan_distribusi(self):
        response = self.client.get(reverse('laporan'), {'jenis_laporan': 'distribusi', 'show_report': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Toko Wisata Purbalingga')

    def test_laporan_pergerakan_stok(self):
        response = self.client.get(reverse('laporan'), {'jenis_laporan': 'pergerakan_stok', 'show_report': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Pergerakan Stok')

    def test_laporan_stok_menipis(self):
        # produk1 total stok 5+3=8 <= minimum 10 (menipis), produk2 total stok 20 > 5 (aman)
        response = self.client.get(reverse('laporan'), {'jenis_laporan': 'stok_menipis', 'show_report': '1'})
        self.assertEqual(response.status_code, 200)
        rows = response.context['laporan_data']['rows']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['kode_produk'], self.produk1.kode_produk)
        self.assertEqual(rows[0]['nama_produk'], self.produk1.nama_produk)

    def test_laporan_rekapitulasi(self):
        response = self.client.get(reverse('laporan'), {'jenis_laporan': 'rekapitulasi', 'show_report': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Kripik Nangka Super')

    def test_laporan_date_filter_presets(self):
        # Preset today
        response = self.client.get(reverse('laporan'), {
            'jenis_laporan': 'barang_masuk',
            'periode_preset': 'today',
            'show_report': '1'
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Hari Ini')

    def test_laporan_empty_data_handled(self):
        # Rentang tanggal di masa depan yang tidak memiliki data
        response = self.client.get(reverse('laporan'), {
            'jenis_laporan': 'barang_masuk',
            'start_date': '2099-01-01',
            'end_date': '2099-01-31',
            'show_report': '1'
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Tidak ada data')

    def test_ekspor_laporan_excel(self):
        response = self.client.get(reverse('ekspor_laporan_excel'), {
            'jenis_laporan': 'stok_saat_ini',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.assertIn('attachment; filename="laporan_stok_saat_ini_', response['Content-Disposition'])

    def test_ekspor_laporan_csv(self):
        response = self.client.get(reverse('ekspor_laporan_csv'), {
            'jenis_laporan': 'barang_masuk',
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue('text/csv' in response['Content-Type'])
        self.assertIn('RUMAH BUMN PURBALINGGA', response.content.decode('utf-8'))




class HapusSemuaDataTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='admin_test', password='password123')
        self.client = Client()
        self.client.login(username='admin_test', password='password123')

        # Siapkan data sampel
        self.umkm = UMKM.objects.create(nama='UMKM Kerajinan Bambu', jenis_usaha='Kriya')
        self.produk = Produk.objects.create(
            kode_produk='PRD-BMB-001',
            nama_produk='Anyaman Bambu Hias',
            umkm=self.umkm,
            harga_beli=15000,
            harga_jual=25000,
            stok_minimum=5
        )
        self.stok, _ = Stok.objects.get_or_create(produk=self.produk, defaults={'stok_kantor': 20})
        self.chanel = Chanel.objects.create(nama_toko='Toko Souvenir Alun-Alun', lokasi='Pusat Kota')
        self.stok_chanel = StokChanel.objects.create(produk=self.produk, chanel=self.chanel, jumlah=10)
        self.distribusi = Distribusi.objects.create(
            produk=self.produk,
            chanel=self.chanel,
            jumlah=5,
            asal='Kantor',
            tujuan=self.chanel.nama_toko
        )
        self.barang_masuk = BarangMasuk.objects.create(
            produk=self.produk,
            jumlah=20,
            asal='Pengrajin',
            tujuan='Kantor'
        )
        self.barang_keluar = BarangKeluar.objects.create(
            produk=self.produk,
            jumlah=5,
            asal='Kantor',
            tujuan='Pembeli Langsung'
        )

    def test_hapus_semua_requires_login(self):
        self.client.logout()
        response = self.client.post(
            reverse('hapus_semua_data', kwargs={'data_type': 'produk'}),
            {'konfirmasi_frasa': 'HAPUS SEMUA DATA'}
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_hapus_semua_requires_post(self):
        response = self.client.get(reverse('hapus_semua_data', kwargs={'data_type': 'umkm'}))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(UMKM.objects.count(), 1)

    def test_hapus_semua_requires_exact_phrase(self):
        # Frasa salah -> data tidak boleh terhapus
        response = self.client.post(
            reverse('hapus_semua_data', kwargs={'data_type': 'umkm'}),
            {'konfirmasi_frasa': 'hapus saja'}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(UMKM.objects.count(), 1)

    def test_hapus_semua_umkm(self):
        response = self.client.post(
            reverse('hapus_semua_data', kwargs={'data_type': 'umkm'}),
            {'konfirmasi_frasa': 'HAPUS SEMUA DATA'}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(UMKM.objects.count(), 0)
        # Produk tidak boleh ikut terhapus, hanya umkm_id yang menjadi None
        self.assertEqual(Produk.objects.count(), 1)
        self.produk.refresh_from_db()
        self.assertIsNone(self.produk.umkm)

    def test_hapus_semua_produk(self):
        response = self.client.post(
            reverse('hapus_semua_data', kwargs={'data_type': 'produk'}),
            {'konfirmasi_frasa': 'HAPUS SEMUA DATA'}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Produk.objects.count(), 0)
        # Data UMKM dan User tidak boleh ikut terhapus
        self.assertEqual(UMKM.objects.count(), 1)
        self.assertEqual(User.objects.count(), 1)

    def test_hapus_semua_kantor(self):
        self.assertEqual(Stok.objects.filter(stok_kantor__gt=0).count(), 1)
        response = self.client.post(
            reverse('hapus_semua_data', kwargs={'data_type': 'kantor'}),
            {'konfirmasi_frasa': 'HAPUS SEMUA DATA'}
        )
        self.assertEqual(response.status_code, 302)
        self.stok.refresh_from_db()
        # Stok kantor menjadi 0
        self.assertEqual(self.stok.stok_kantor, 0)
        # Produk tidak dihapus
        self.assertEqual(Produk.objects.count(), 1)
        # Stok chanel/bazar tidak terhapus
        self.stok_chanel.refresh_from_db()
        self.assertEqual(self.stok_chanel.jumlah, 10)

    def test_hapus_semua_chanel(self):
        response = self.client.post(
            reverse('hapus_semua_data', kwargs={'data_type': 'chanel'}),
            {'konfirmasi_frasa': 'HAPUS SEMUA DATA'}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Chanel.objects.count(), 0)
        # Produk dan UMKM tidak terhapus
        self.assertEqual(Produk.objects.count(), 1)
        self.assertEqual(UMKM.objects.count(), 1)

    def test_hapus_semua_distribusi(self):
        response = self.client.post(
            reverse('hapus_semua_data', kwargs={'data_type': 'distribusi'}),
            {'konfirmasi_frasa': 'HAPUS SEMUA DATA'}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Distribusi.objects.count(), 0)
        # Produk, Stok, dan Chanel tetap aman
        self.assertEqual(Produk.objects.count(), 1)
        self.assertEqual(Chanel.objects.count(), 1)

    def test_hapus_semua_barang_masuk(self):
        response = self.client.post(
            reverse('hapus_semua_data', kwargs={'data_type': 'barang_masuk'}),
            {'konfirmasi_frasa': 'HAPUS SEMUA DATA'}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(BarangMasuk.objects.count(), 0)
        self.assertEqual(Produk.objects.count(), 1)

    def test_hapus_semua_barang_keluar(self):
        response = self.client.post(
            reverse('hapus_semua_data', kwargs={'data_type': 'barang_keluar'}),
            {'konfirmasi_frasa': 'HAPUS SEMUA DATA'}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(BarangKeluar.objects.count(), 0)
        self.assertEqual(Produk.objects.count(), 1)

    def test_hapus_semua_does_not_delete_admin_users(self):
        # Pastikan akun admin/pengguna tidak terhapus saat aksi hapus semua data dijalankan
        for dt in ['umkm', 'produk', 'kantor', 'chanel', 'distribusi', 'barang_masuk', 'barang_keluar']:
            self.client.post(
                reverse('hapus_semua_data', kwargs={'data_type': dt}),
                {'konfirmasi_frasa': 'HAPUS SEMUA DATA'}
            )
        self.assertTrue(User.objects.filter(username='admin_test').exists())
