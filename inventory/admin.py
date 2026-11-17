from django.contrib import admin
from .models import UMKM, Produk, Stok, Distribusi


@admin.register(UMKM)
class UMKMAdmin(admin.ModelAdmin):
    list_display = ('nama', 'jenis_usaha', 'kontak')
    search_fields = ('nama', 'jenis_usaha')


@admin.register(Produk)
class ProdukAdmin(admin.ModelAdmin):
    list_display = (
        'kode_produk',
        'nama_produk',
        'nama_pemilik',
        'umkm',
        'kategori',
        'harga_beli',
        'harga_jual',
        'stok_minimum',
    )
    search_fields = ('kode_produk', 'nama_produk', 'nama_pemilik')
    list_filter = ('kategori',)

@admin.register(Stok)
class StokAdmin(admin.ModelAdmin):
    list_display = (
        'produk',
        'stok_kantor',
        'stok_bazar',
        'total_stok',
    )
    search_fields = (
        'produk__kode_produk',
        'produk__nama_produk',
    )


@admin.register(Distribusi)
class DistribusiAdmin(admin.ModelAdmin):
    list_display = (
        'produk',
        'jumlah',
        'tanggal',
    
    )
    search_fields = (
        'produk__kode_produk',
        'produk__nama_produk',
    )
    list_filter = ('tanggal',)