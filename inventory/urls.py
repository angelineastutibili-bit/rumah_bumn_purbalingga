from django.urls import path
from django.contrib.auth.views import LoginView
from . import views

urlpatterns = [
    # AUTHENTICATION
    path('login/', LoginView.as_view(template_name='inventory/login.html', redirect_authenticated_user=True), name='login'),
    path('logout/', views.user_logout, name='logout'),

    # DASHBOARD
    path('', views.dashboard, name='dashboard'),

    # DATA UMKM
    path('umkm/', views.data_umkm, name='data_umkm'),
    path('umkm/tambah/', views.tambah_umkm, name='tambah_umkm'),
    path('umkm/<int:umkm_id>/', views.detail_umkm, name='detail_umkm'),
    path('umkm/edit/<int:umkm_id>/', views.edit_umkm, name='edit_umkm'),
    path('umkm/hapus/<int:umkm_id>/', views.hapus_umkm, name='hapus_umkm'),

    # DATA PRODUK
    path('produk/', views.data_produk, name='data_produk'),
    path('produk/tambah/', views.tambah_produk, name='tambah_produk'),
    path('produk/<int:produk_id>/', views.detail_produk, name='detail_produk'),
    path('produk/edit/<int:produk_id>/', views.edit_produk, name='edit_produk'),
    path('produk/hapus/<int:produk_id>/', views.hapus_produk, name='hapus_produk'),

    # STOK & RIWAYAT
    path('stok/', views.data_stok, name='data_stok'),
    path('stok/edit/<int:stok_id>/', views.edit_stok, name='edit_stok'),
    path('stok/riwayat/', views.riwayat_stok_view, name='riwayat_stok'),

    # KANTOR
    path('kantor/', views.data_kantor, name='data_kantor'),

    # CHANEL
    path('chanel/', views.data_bazar, name='data_bazar'),
    path('chanel/seluruh-bazar/', views.chanel_seluruh_bazar, name='chanel_seluruh_bazar'),
    path('chanel/tambah/', views.tambah_chanel, name='tambah_chanel'),
    path('chanel/<int:chanel_id>/', views.detail_chanel, name='detail_chanel'),
    path('chanel/<int:chanel_id>/edit/', views.edit_chanel, name='edit_chanel'),
    path('chanel/<int:chanel_id>/hapus/', views.hapus_chanel, name='hapus_chanel'),
    path('chanel/<int:chanel_id>/tambah-stok/', views.tambah_stok_chanel, name='tambah_stok_chanel'),
    path('chanel/<int:chanel_id>/stok/tambah/', views.tambah_stok_chanel, name='tambah_stok_chanel_alt'),
    path('chanel/stok/<int:stok_id>/edit/', views.edit_stok_chanel, name='edit_stok_chanel'),
    path('chanel/stok/<int:stok_id>/hapus/', views.hapus_stok_chanel, name='hapus_stok_chanel'),

    # DISTRIBUSI
    path('distribusi/', views.data_distribusi, name='data_distribusi'),
    path('distribusi/tambah/', views.tambah_distribusi, name='tambah_distribusi'),
    path('distribusi/edit/<int:distribusi_id>/', views.edit_distribusi, name='edit_distribusi'),
    path('distribusi/hapus/<int:distribusi_id>/', views.hapus_distribusi, name='hapus_distribusi'),
    # SURAT JALAN for a distribusi record
    path('distribusi/<int:distribusi_id>/surat-jalan/', views.surat_jalan_view, name='surat_jalan'),
    path('distribusi/<int:distribusi_id>/surat-jalan/pdf/', views.surat_jalan_pdf, name='surat_jalan_pdf'),

    # BARANG MASUK
    path('barang_masuk/', views.data_barang_masuk, name='data_barang_masuk'),
    path('barang_masuk/tambah/', views.tambah_barang_masuk, name='tambah_barang_masuk'),

    # BARANG KELUAR
    path('barang_keluar/', views.data_barang_keluar, name='data_barang_keluar'),
    path('barang_keluar/tambah/', views.tambah_barang_keluar, name='tambah_barang_keluar'),

    # LAPORAN & EKSPOR
    path('laporan/', views.laporan, name='laporan'),
    path('laporan/ekspor/excel/', views.ekspor_laporan_excel, name='ekspor_laporan_excel'),
    path('laporan/ekspor/csv/', views.ekspor_laporan_csv, name='ekspor_laporan_csv'),
    path('ekspor/<str:data_type>/', views.ekspor_csv, name='ekspor_csv'),

    # FITUR HAPUS SEMUA DATA
    path('hapus-semua/<str:data_type>/', views.hapus_semua_data, name='hapus_semua_data'),
    path('umkm/hapus-semua/', views.hapus_semua_data, {'data_type': 'umkm'}, name='hapus_semua_umkm'),
    path('produk/hapus-semua/', views.hapus_semua_data, {'data_type': 'produk'}, name='hapus_semua_produk'),
    path('kantor/hapus-semua/', views.hapus_semua_data, {'data_type': 'kantor'}, name='hapus_semua_kantor'),
    path('stok/hapus-semua/', views.hapus_semua_data, {'data_type': 'stok'}, name='hapus_semua_stok'),
    path('chanel/hapus-semua/', views.hapus_semua_data, {'data_type': 'chanel'}, name='hapus_semua_chanel'),
    path('distribusi/hapus-semua/', views.hapus_semua_data, {'data_type': 'distribusi'}, name='hapus_semua_distribusi'),
    path('barang_masuk/hapus-semua/', views.hapus_semua_data, {'data_type': 'barang_masuk'}, name='hapus_semua_barang_masuk'),
    path('barang_keluar/hapus-semua/', views.hapus_semua_data, {'data_type': 'barang_keluar'}, name='hapus_semua_barang_keluar'),

    # API GRAFIK DASHBOARD
    path('api/grafik-pergerakan-stok/', views.api_grafik_pergerakan_stok, name='api_grafik_pergerakan_stok'),
]
