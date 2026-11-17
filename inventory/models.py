from django.db import models
from django.db.models import Sum
from django.utils import timezone


class UMKM(models.Model):
    nama = models.CharField(max_length=200)
    pemilik = models.CharField(max_length=150, blank=True, null=True)
    jenis_usaha = models.CharField(max_length=100)
    alamat = models.TextField(blank=True, null=True)
    kontak = models.CharField(max_length=50, blank=True, null=True)
    tanggal_terdaftar = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['nama']
        verbose_name = 'UMKM',
        verbose_name_plural =   'Data UMKM'

    def __str__(self):
        return self.nama

    @property
    def total_produk(self):
        return self.produk.count()


class Produk(models.Model):
    kode_produk = models.CharField(max_length=50, unique=True)
    nama_produk = models.CharField(max_length=200)
    nama_pemilik = models.CharField(max_length=200, blank=True, null=True)
    umkm = models.ForeignKey(
        UMKM,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='produk'
    )
    kategori = models.CharField(max_length=100, blank=True, null=True)
    harga_beli = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    harga_jual = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    stok_minimum = models.PositiveIntegerField(default=1)
    keterangan = models.TextField(blank=True, null=True)
    tanggal_dibuat = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nama_produk']

    def __str__(self):
        return self.nama_produk

    @property
    def stok_kantor(self):
        if hasattr(self, 'stok'):
            return self.stok.stok_kantor
        return 0

    @property
    def stok_chanel_total(self):
        total = self.stok_chanel.aggregate(total=Sum('jumlah'))['total']
        return total or 0

    @property
    def total_stok_semua(self):
        return self.stok_kantor + self.stok_chanel_total

    @property
    def status_stok(self):
        total = self.total_stok_semua
        if total <= 0:
            return 'habis'
        elif total <= self.stok_minimum:
            return 'menipis'
        return 'aman'


class Stok(models.Model):
    produk = models.OneToOneField(
        Produk,
        on_delete=models.CASCADE,
        related_name='stok'
    )
    stok_kantor = models.PositiveIntegerField(default=0)
    stok_bazar = models.PositiveIntegerField(default=0)

    @property
    def stok_chanel(self):
        total = self.produk.stok_chanel.aggregate(total=Sum('jumlah'))['total']
        return total or 0

    @property
    def total_stok(self):
        return self.stok_kantor + self.stok_chanel

    @property
    def status(self):
        tot = self.total_stok
        if tot <= 0:
            return 'Habis'
        elif tot <= self.produk.stok_minimum:
            return 'Menipis'
        return 'Aman'

    def __str__(self):
        return f"Stok {self.produk.nama_produk}"


class Chanel(models.Model):
    nama_toko = models.CharField(max_length=150, unique=True)
    lokasi = models.CharField(max_length=255, blank=True, null=True)
    keterangan = models.TextField(blank=True, null=True)
    aktif = models.BooleanField(default=True)
    tanggal_dibuat = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['nama_toko']
        verbose_name = 'Chanel'
        verbose_name_plural = 'Data Chanel'

    def __str__(self):
        return self.nama_toko

    @property
    def total_stok(self):
        total = self.stok_produk.aggregate(total=Sum('jumlah'))['total']
        return total or 0

    @property
    def total_produk_jenis(self):
        return self.stok_produk.count()


class StokChanel(models.Model):
    produk = models.ForeignKey(
        Produk,
        on_delete=models.CASCADE,
        related_name='stok_chanel'
    )
    chanel = models.ForeignKey(
        Chanel,
        on_delete=models.CASCADE,
        related_name='stok_produk'
    )
    jumlah = models.PositiveIntegerField(default=0)
    tanggal_diperbarui = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['produk__nama_produk']
        constraints = [
            models.UniqueConstraint(
                fields=['produk', 'chanel'],
                name='unik_produk_per_chanel'
            )
        ]

    def __str__(self):
        return f"{self.produk.nama_produk} - {self.chanel.nama_toko} ({self.jumlah})"


class Distribusi(models.Model):
    produk = models.ForeignKey(
        Produk,
        on_delete=models.CASCADE,
        related_name='distribusi'
    )
    chanel = models.ForeignKey(
        Chanel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='distribusi'
    )
    jumlah = models.PositiveIntegerField(default=0)
    asal = models.CharField(max_length=150, default='Kantor')
    tujuan = models.CharField(max_length=150, blank=True, null=True)
    keterangan = models.TextField(blank=True, null=True)
    tanggal = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-tanggal']

    def __str__(self):
        tujuan_str = self.chanel.nama_toko if self.chanel else (self.tujuan or 'Chanel')
        return f"Distribusi {self.produk.nama_produk} ({self.jumlah}) -> {tujuan_str}"


# Alias for backward compatibility
distribusi = Distribusi

# -------------------------------------------------
# SURAT JALAN
# -------------------------------------------------
class SuratJalan(models.Model):
    nomor = models.CharField(max_length=25, unique=True)
    tanggal = models.DateTimeField(auto_now_add=True)
    distribusi = models.OneToOneField(
        Distribusi,
        on_delete=models.CASCADE,
        related_name='surat_jalan',
    )
    pengirim = models.CharField(max_length=200, default='Rumah BUMN Purbalingga', blank=True)
    penerima = models.CharField(max_length=200, blank=True, null=True)
    alamat_tujuan = models.TextField(blank=True, null=True)
    keterangan = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-tanggal']
        verbose_name = 'Surat Jalan'
        verbose_name_plural = 'Surat Jalan'

    def __str__(self):
        return f"{self.nomor} - {self.distribusi}"

    def save(self, *args, **kwargs):
        if not self.nomor:
            self.nomor = self._generate_nomor()
        elif self.pk:
            existing = SuratJalan.objects.filter(nomor__iexact=self.nomor).exclude(pk=self.pk).exists()
            if existing:
                raise ValueError(f"Nomor surat jalan '{self.nomor}' sudah digunakan.")
        super().save(*args, **kwargs)

    def _generate_nomor(self):
        from django.utils import timezone
        year = timezone.now().strftime('%Y')
        prefix = f'SJ-{year}'
        with transaction.atomic():
            latest = SuratJalan.objects.select_for_update().filter(nomor__startswith=prefix).order_by('-nomor').first()
            if latest and latest.nomor:
                try:
                    seq = int(latest.nomor.split('-')[-1]) + 1
                except (TypeError, ValueError):
                    seq = 1
            else:
                seq = 1

            candidate = f"{prefix}-{seq:03d}"
            counter = seq + 1
            while SuratJalan.objects.filter(nomor=candidate).exists():
                candidate = f"{prefix}-{counter:03d}"
                counter += 1
            return candidate


class BarangMasuk(models.Model):
    produk = models.ForeignKey(
        Produk,
        on_delete=models.CASCADE,
        related_name='barang_masuk'
    )
    jumlah = models.PositiveIntegerField(default=0)
    asal = models.CharField(max_length=150, blank=True, null=True)
    tujuan = models.CharField(max_length=150, default='Kantor')
    keterangan = models.TextField(blank=True, null=True)
    tanggal = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-tanggal']

    def __str__(self):
        return f"Masuk {self.produk.nama_produk} ({self.jumlah})"


class BarangKeluar(models.Model):
    produk = models.ForeignKey(
        Produk,
        on_delete=models.CASCADE,
        related_name='barang_keluar'
    )
    jumlah = models.PositiveIntegerField(default=0)
    asal = models.CharField(max_length=150, default='Kantor')
    tujuan = models.CharField(max_length=150, blank=True, null=True)
    keterangan = models.TextField(blank=True, null=True)
    tanggal = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-tanggal']

    def __str__(self):
        return f"Keluar {self.produk.nama_produk} ({self.jumlah})"


class RiwayatStok(models.Model):
    JENIS_CHOICES = [
        ('MASUK', 'Barang Masuk'),
        ('KELUAR', 'Barang Keluar'),
        ('DISTRIBUSI', 'Distribusi ke Chanel'),
        ('KEMBALI_DISTRIBUSI', 'Pembatalan Distribusi'),
        ('PENYESUAIAN', 'Penyesuaian Manual'),
    ]

    produk = models.ForeignKey(
        Produk,
        on_delete=models.CASCADE,
        related_name='riwayat_stok'
    )
    jenis_transaksi = models.CharField(max_length=50, choices=JENIS_CHOICES)
    jumlah = models.IntegerField(help_text="Jumlah stok yang bertambah (+) atau berkurang (-)")
    stok_sebelum = models.IntegerField(default=0)
    stok_sesudah = models.IntegerField(default=0)
    lokasi = models.CharField(max_length=150, default='Kantor')
    keterangan = models.TextField(blank=True, null=True)
    tanggal = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-tanggal']
        verbose_name = 'Riwayat Stok'
        verbose_name_plural = 'Riwayat Stok'

    def __str__(self):
        return f"[{self.jenis_transaksi}] {self.produk.nama_produk} ({self.jumlah:+d}) pada {self.tanggal.strftime('%d-%m-%Y %H:%M')}"