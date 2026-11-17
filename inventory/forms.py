from django import forms
from django.utils import timezone
from .models import UMKM, Produk, Stok, Distribusi, Chanel, StokChanel, BarangMasuk, BarangKeluar, SuratJalan


class UMKMForm(forms.ModelForm):
    class Meta:
        model = UMKM
        fields = ['nama', 'pemilik', 'jenis_usaha', 'alamat', 'kontak', 'tanggal_terdaftar']
        widgets = {
            'nama': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nama UMKM / Usaha', 'required': True}),
            'pemilik': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nama Pemilik'}),
            'jenis_usaha': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contoh: Makanan, Fashion, Kerajinan', 'required': True}),
            'alamat': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Alamat UMKM'}),
            'kontak': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nomor Telepon / WhatsApp'}),
            'tanggal_terdaftar': forms.DateTimeInput(
                attrs={'class': 'form-control', 'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M'
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tanggal_terdaftar'].required = False
        self.fields['tanggal_terdaftar'].input_formats = [
            '%Y-%m-%dT%H:%M',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M',
            '%Y-%m-%d',
        ]
        if not self.instance.pk and not self.initial.get('tanggal_terdaftar'):
            self.initial['tanggal_terdaftar'] = timezone.localtime(timezone.now()).strftime('%Y-%m-%dT%H:%M')
        elif self.instance.pk and self.instance.tanggal_terdaftar:
            self.initial['tanggal_terdaftar'] = timezone.localtime(self.instance.tanggal_terdaftar).strftime('%Y-%m-%dT%H:%M')

    def clean_tanggal_terdaftar(self):
        tgl = self.cleaned_data.get('tanggal_terdaftar')
        if not tgl:
            return timezone.now()
        return tgl


class ProdukForm(forms.ModelForm):
    class Meta:
        model = Produk
        fields = [
            'kode_produk',
            'nama_produk',
            'nama_pemilik',
            'umkm',
            'kategori',
            'harga_beli',
            'harga_jual',
            'stok_minimum',
            'keterangan'
        ]
        widgets = {
            'kode_produk': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Kode Unik Produk (cth: PRD001)', 'required': True}),
            'nama_produk': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nama Produk Lengkap', 'required': True}),
            'nama_pemilik': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nama Pemilik Produk'}),
            'umkm': forms.Select(attrs={'class': 'form-control'}),
            'kategori': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Kategori (cth: Makanan, Minuman)'}),
            'harga_beli': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '500', 'placeholder': 'Harga Beli (Rp)'}),
            'harga_jual': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '500', 'placeholder': 'Harga Jual (Rp)'}),
            'stok_minimum': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'placeholder': 'Batas Stok Minimum'}),
            'keterangan': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Keterangan tambahan'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk and 'stok_minimum' not in self.initial:
            self.initial['stok_minimum'] = 1

    def clean_harga_beli(self):
        harga = self.cleaned_data.get('harga_beli')
        if harga is not None and harga < 0:
            raise forms.ValidationError("Harga beli tidak boleh negatif.")
        return harga

    def clean_harga_jual(self):
        harga = self.cleaned_data.get('harga_jual')
        if harga is not None and harga < 0:
            raise forms.ValidationError("Harga jual tidak boleh negatif.")
        return harga

    def clean_stok_minimum(self):
        stok_min = self.cleaned_data.get('stok_minimum')
        if stok_min is not None and stok_min < 0:
            raise forms.ValidationError("Stok minimum tidak boleh negatif.")
        return stok_min

    def clean_kode_produk(self):
        kode = self.cleaned_data.get('kode_produk')
        if kode:
            kode = kode.strip()
            qs = Produk.objects.filter(kode_produk__iexact=kode)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(f"Kode produk '{kode}' sudah digunakan. Silakan gunakan kode lain.")
        return kode


class DistribusiForm(forms.ModelForm):
    class Meta:
        model = Distribusi
        fields = ['produk', 'chanel', 'jumlah', 'keterangan']
        widgets = {
            'produk': forms.Select(attrs={'class': 'form-control', 'required': True}),
            'chanel': forms.Select(attrs={'class': 'form-control', 'required': True}),
            'jumlah': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'required': True, 'placeholder': 'Jumlah item yang didistribusikan'}),
            'keterangan': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Catatan / tujuan pengiriman'}),
        }

    def clean_jumlah(self):
        jumlah = self.cleaned_data.get('jumlah')
        if not jumlah or jumlah <= 0:
            raise forms.ValidationError("Jumlah distribusi harus lebih dari 0.")
        return jumlah


class ChanelForm(forms.ModelForm):
    class Meta:
        model = Chanel
        fields = ['nama_toko', 'lokasi', 'keterangan', 'aktif']
        widgets = {
            'nama_toko': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nama Toko / Chanel', 'required': True}),
            'lokasi': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Lokasi / Alamat Toko'}),
            'keterangan': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Keterangan tambahan'}),
            'aktif': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class StokChanelForm(forms.ModelForm):
    class Meta:
        model = StokChanel
        fields = ['jumlah']
        widgets = {
            'jumlah': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'required': True}),
        }

    def clean_jumlah(self):
        jumlah = self.cleaned_data.get('jumlah')
        if jumlah is not None and jumlah < 0:
            raise forms.ValidationError("Jumlah stok tidak boleh kurang dari 0.")
        return jumlah


class BarangMasukForm(forms.ModelForm):
    class Meta:
        model = BarangMasuk
        fields = ['produk', 'jumlah', 'asal', 'keterangan']
        widgets = {
            'produk': forms.Select(attrs={'class': 'form-control', 'required': True}),
            'jumlah': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'required': True, 'placeholder': 'Jumlah barang masuk'}),
            'asal': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Asal barang (cth: Pengrajin, UMKM, Supplier)'}),
            'keterangan': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Catatan penerimaan'}),
        }

    def clean_jumlah(self):
        jumlah = self.cleaned_data.get('jumlah')
        if not jumlah or jumlah <= 0:
            raise forms.ValidationError("Jumlah harus lebih dari 0.")
        return jumlah


class BarangKeluarForm(forms.ModelForm):
    class Meta:
        model = BarangKeluar
        fields = ['produk', 'jumlah', 'tujuan', 'keterangan']
        widgets = {
            'produk': forms.Select(attrs={'class': 'form-control', 'required': True}),
            'jumlah': forms.NumberInput(attrs={'class': 'form-control', 'min': '1', 'required': True, 'placeholder': 'Jumlah barang keluar'}),
            'tujuan': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Tujuan barang keluar (cth: Penjualan Langsung, Pameran)'}),
            'keterangan': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Catatan pengeluaran'}),
        }

    def clean_jumlah(self):
        jumlah = self.cleaned_data.get('jumlah')
        if not jumlah or jumlah <= 0:
            raise forms.ValidationError("Jumlah harus lebih dari 0.")
        return jumlah


class SuratJalanForm(forms.ModelForm):
    class Meta:
        model = SuratJalan
        fields = ['nomor', 'pengirim', 'penerima', 'alamat_tujuan', 'keterangan']
        widgets = {
            'nomor': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contoh: SJ-2026-001', 'required': True}),
            'pengirim': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nama pengirim', 'required': True}),
            'penerima': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nama penerima'}),
            'alamat_tujuan': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Alamat tujuan pengiriman'}),
            'keterangan': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Catatan tambahan'}),
        }

    def clean_nomor(self):
        nomor = (self.cleaned_data.get('nomor') or '').strip()
        if not nomor:
            raise forms.ValidationError('Nomor surat jalan tidak boleh kosong.')

        qs = SuratJalan.objects.filter(nomor__iexact=nomor)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f"Nomor surat jalan '{nomor}' sudah digunakan. Silakan pilih nomor lain.")
        return nomor

    def clean_pengirim(self):
        pengirim = (self.cleaned_data.get('pengirim') or '').strip()
        if not pengirim:
            raise forms.ValidationError('Nama pengirim wajib diisi.')
        return pengirim
