import csv
import json
import os
from datetime import datetime
from decimal import Decimal
from django import forms
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, Sum
from django.db.models.functions import TruncDate, TruncMonth, TruncYear
from django.http import HttpResponse, JsonResponse
from django.template.loader import get_template, render_to_string
from django.conf import settings
from django.views.decorators.http import require_http_methods
from io import BytesIO
from xhtml2pdf import pisa

# Perbaikan pada daftar import model
from .models import (
    UMKM,
    Produk,
    Stok,
    Distribusi,
    BarangMasuk,
    BarangKeluar,
    Chanel,
    StokChanel,
    RiwayatStok,
    SuratJalan,
)

# Perbaikan pada daftar import forms
from .forms import (
    UMKMForm,
    ProdukForm,
    DistribusiForm,
    ChanelForm,
    StokChanelForm,
    BarangMasukForm,
    BarangKeluarForm,
    SuratJalanForm,
)

# ==================================================
# DASHBOARD
# ==================================================

@login_required
def dashboard(request):
    import json
    from datetime import date

    total_produk = Produk.objects.count()
    total_umkm = UMKM.objects.count()

    # Hitung total stok aktual
    stok_kantor_total = Stok.objects.aggregate(total=Sum('stok_kantor'))['total'] or 0
    stok_chanel_total = StokChanel.objects.aggregate(total=Sum('jumlah'))['total'] or 0

    # Riwayat terbaru
    riwayat_masuk = BarangMasuk.objects.select_related('produk').order_by('-tanggal')[:5]
    riwayat_keluar = BarangKeluar.objects.select_related('produk').order_by('-tanggal')[:5]
    riwayat_distribusi = Distribusi.objects.select_related('produk', 'chanel').order_by('-tanggal')[:5]

    # Produk dengan stok menipis / kritis di kantor
    semua_stok = Stok.objects.select_related('produk', 'produk__umkm').all()
    produk_stok_rendah = [
        item for item in semua_stok
        if item.stok_kantor <= item.produk.stok_minimum
    ][:10]

    # Data grafik: stok per produk (dari database, bukan dummy)
    chart_labels = []
    chart_kantor = []
    chart_chanel = []
    for stok_obj in Stok.objects.select_related('produk').all():
        nama = stok_obj.produk.nama_produk[:20]  # potong nama panjang
        chart_labels.append(nama)
        chart_kantor.append(stok_obj.stok_kantor)
        chanel_val = StokChanel.objects.filter(
            produk=stok_obj.produk
        ).aggregate(total=Sum('jumlah'))['total'] or 0
        chart_chanel.append(chanel_val)

    context = {
        'total_produk': total_produk,
        'total_umkm': total_umkm,
        'stok_kantor': stok_kantor_total,
        'stok_chanel': stok_chanel_total,
        'stok_bazar': stok_chanel_total,  # kompatibilitas jika template lama memanggil
        'riwayat_masuk': riwayat_masuk,
        'riwayat_keluar': riwayat_keluar,
        'riwayat_distribusi': riwayat_distribusi,
        'produk_stok_rendah': produk_stok_rendah,
        'chart_labels': json.dumps(chart_labels),
        'chart_kantor': json.dumps(chart_kantor),
        'chart_chanel': json.dumps(chart_chanel),
        'today_date': date.today(),
    }

    return render(request, 'inventory/dashboard.html', context)


@login_required
def api_grafik_pergerakan_stok(request):
    """
    API endpoint untuk data grafik pergerakan stok.
    Parameter: ?periode=harian|bulanan|tahunan
    Mengembalikan JSON berisi labels, data stok_masuk, stok_keluar, distribusi.
    Distribusi diambil dari model Distribusi (bukan BarangKeluar) untuk
    menghindari perhitungan ganda.
    """
    periode = request.GET.get('periode', 'bulanan').lower()

    if periode == 'harian':
        trunc_fn = TruncDate
        date_format = lambda d: d.strftime('%d/%m/%Y') if d else ''
    elif periode == 'tahunan':
        trunc_fn = TruncYear
        date_format = lambda d: str(d.year) if d else ''
    else:  # bulanan (default)
        trunc_fn = TruncMonth
        date_format = lambda d: d.strftime('%b %Y') if d else ''

    # ---- Stok Masuk (dari BarangMasuk) ----
    masuk_qs = (
        BarangMasuk.objects
        .annotate(periode_key=trunc_fn('tanggal'))
        .values('periode_key')
        .annotate(total=Sum('jumlah'))
        .order_by('periode_key')
    )

    # ---- Stok Keluar MURNI (dari BarangKeluar, TIDAK termasuk distribusi) ----
    keluar_qs = (
        BarangKeluar.objects
        .annotate(periode_key=trunc_fn('tanggal'))
        .values('periode_key')
        .annotate(total=Sum('jumlah'))
        .order_by('periode_key')
    )

    # ---- Distribusi (dari model Distribusi, TERPISAH dari barang keluar) ----
    distribusi_qs = (
        Distribusi.objects
        .annotate(periode_key=trunc_fn('tanggal'))
        .values('periode_key')
        .annotate(total=Sum('jumlah'))
        .order_by('periode_key')
    )

    # Kumpulkan semua periode unik (gabungkan dari ketiga query)
    semua_periode = set()
    masuk_map = {}
    keluar_map = {}
    distribusi_map = {}

    for row in masuk_qs:
        k = row['periode_key']
        masuk_map[k] = row['total'] or 0
        semua_periode.add(k)

    for row in keluar_qs:
        k = row['periode_key']
        keluar_map[k] = row['total'] or 0
        semua_periode.add(k)

    for row in distribusi_qs:
        k = row['periode_key']
        distribusi_map[k] = row['total'] or 0
        semua_periode.add(k)

    # Urutkan periode
    semua_periode_sorted = sorted([p for p in semua_periode if p is not None])

    labels = [date_format(p) for p in semua_periode_sorted]
    data_masuk = [masuk_map.get(p, 0) for p in semua_periode_sorted]
    data_keluar = [keluar_map.get(p, 0) for p in semua_periode_sorted]
    data_distribusi = [distribusi_map.get(p, 0) for p in semua_periode_sorted]

    return JsonResponse({
        'labels': labels,
        'stok_masuk': data_masuk,
        'stok_keluar': data_keluar,
        'distribusi': data_distribusi,
        'has_data': len(labels) > 0,
    })


@login_required
def surat_jalan_view(request, distribusi_id):
    """Render halaman Surat Jalan untuk transaksi distribusi tertentu."""
    distribusi = get_object_or_404(
        Distribusi.objects.select_related('produk', 'chanel'),
        id=distribusi_id,
    )
    surat, _ = SuratJalan.objects.get_or_create(distribusi=distribusi)
    if not surat.nomor:
        surat.nomor = surat._generate_nomor()
        surat.save(update_fields=['nomor'])

    context = {
        'surat': surat,
        'distribusi': distribusi,
    }
    return render(request, 'inventory/surat_jalan.html', context)


@login_required
def surat_jalan_pdf(request, distribusi_id):
    """Generate PDF Surat Jalan berdasarkan distribusi yang dipilih."""
    distribusi = get_object_or_404(
        Distribusi.objects.select_related('produk', 'chanel'),
        id=distribusi_id,
    )
    surat, _ = SuratJalan.objects.get_or_create(distribusi=distribusi)
    if not surat.nomor:
        surat.nomor = surat._generate_nomor()
        surat.save(update_fields=['nomor'])

    context = {
        'surat': surat,
        'distribusi': distribusi,
    }
    html = render_to_string('inventory/surat_jalan_pdf.html', context)

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="surat_jalan_{surat.nomor}.pdf"'

    buffer = BytesIO()
    pdf_status = pisa.CreatePDF(
        BytesIO(html.encode('UTF-8')),
        buffer,
        encoding='utf-8',
    )

    if pdf_status.err:
        return HttpResponse('Gagal membuat PDF Surat Jalan.', status=500)

    response.write(buffer.getvalue())
    return response


# ==================================================
# DATA UMKM
# ==================================================

@login_required
def data_umkm(request):
    query = request.GET.get('q', '').strip()
    if query:
        umkm_list = UMKM.objects.filter(
            Q(nama__icontains=query) |
            Q(pemilik__icontains=query) |
            Q(jenis_usaha__icontains=query) |
            Q(alamat__icontains=query) |
            Q(kontak__icontains=query)
        )
    else:
        umkm_list = UMKM.objects.all()

    return render(request, 'inventory/data_umkm.html', {
        'umkm': umkm_list,
        'query': query,
    })


@login_required
def detail_umkm(request, umkm_id):
    umkm = get_object_or_404(UMKM, id=umkm_id)
    produk_list = umkm.produk.all()
    return render(request, 'inventory/detail_umkm.html', {
        'umkm': umkm,
        'produk_list': produk_list,
    })


@login_required
def tambah_umkm(request):
    if request.method == 'POST':
        form = UMKMForm(request.POST)
        if form.is_valid():
            umkm = form.save()
            messages.success(request, f"UMKM '{umkm.nama}' berhasil ditambahkan.")
            return redirect('data_umkm')
        else:
            messages.error(request, "Gagal menambahkan UMKM. Periksa input data.")
    else:
        form = UMKMForm()

    return render(request, 'inventory/tambah_umkm.html', {'form': form})


@login_required
def edit_umkm(request, umkm_id):
    umkm = get_object_or_404(UMKM, id=umkm_id)
    if request.method == 'POST':
        form = UMKMForm(request.POST, instance=umkm)
        if form.is_valid():
            form.save()
            messages.success(request, f"Data UMKM '{umkm.nama}' berhasil diperbarui.")
            return redirect('data_umkm')
        else:
            messages.error(request, "Gagal memperbarui data UMKM.")
    else:
        form = UMKMForm(instance=umkm)

    return render(request, 'inventory/edit_umkm.html', {'form': form, 'umkm': umkm})


@login_required
def hapus_umkm(request, umkm_id):
    umkm = get_object_or_404(UMKM, id=umkm_id)
    nama = umkm.nama
    umkm.delete()
    messages.success(request, f"UMKM '{nama}' berhasil dihapus.")
    return redirect('data_umkm')


# ==================================================
# DATA PRODUK
# ==================================================

@login_required
def data_produk(request):
    query = request.GET.get('q', '').strip()
    kategori_filter = request.GET.get('kategori', '').strip()

    produk_list = Produk.objects.select_related('umkm').all()

    if query:
        produk_list = produk_list.filter(
            Q(kode_produk__icontains=query) |
            Q(nama_produk__icontains=query) |
            Q(nama_pemilik__icontains=query) |
            Q(umkm__nama__icontains=query) |
            Q(kategori__icontains=query)
        )

    if kategori_filter:
        produk_list = produk_list.filter(kategori__iexact=kategori_filter)

    kategori_list = Produk.objects.values_list('kategori', flat=True).distinct()

    return render(request, 'inventory/data_produk.html', {
        'produk': produk_list,
        'query': query,
        'kategori_filter': kategori_filter,
        'kategori_list': [k for k in kategori_list if k],
    })


@login_required
def detail_produk(request, produk_id):
    produk = get_object_or_404(Produk.objects.select_related('umkm'), id=produk_id)
    stok, _ = Stok.objects.get_or_create(produk=produk, defaults={'stok_kantor': 0, 'stok_bazar': 0})
    stok_per_chanel = StokChanel.objects.filter(produk=produk).select_related('chanel')
    riwayat = RiwayatStok.objects.filter(produk=produk)[:10]

    return render(request, 'inventory/detail_produk.html', {
        'produk': produk,
        'stok': stok,
        'stok_per_chanel': stok_per_chanel,
        'riwayat': riwayat,
    })


@login_required
def tambah_produk(request):
    selected_umkm_id = request.GET.get('umkm_id') or request.POST.get('umkm_id')
    selected_umkm = None
    if selected_umkm_id:
        selected_umkm = get_object_or_404(UMKM, id=selected_umkm_id)

    if request.method == 'POST':
        post_data = request.POST.copy()
        if selected_umkm:
            post_data['umkm'] = str(selected_umkm.id)
        form = ProdukForm(post_data)
        if form.is_valid():
            with transaction.atomic():
                produk = form.save()
                Stok.objects.get_or_create(
                    produk=produk,
                    defaults={'stok_kantor': 0, 'stok_bazar': 0}
                )
            if selected_umkm:
                messages.success(request, f"Produk '{produk.nama_produk}' berhasil ditambahkan ke UMKM '{selected_umkm.nama}'.")
                return redirect('detail_umkm', umkm_id=selected_umkm.id)
            messages.success(request, f"Produk '{produk.nama_produk}' berhasil ditambahkan.")
            return redirect('data_produk')
        else:
            messages.error(request, "Gagal menambahkan produk. Periksa kembali form.")
    else:
        form = ProdukForm(initial={'umkm': selected_umkm.id if selected_umkm else None})

    if selected_umkm:
        form.fields['umkm'].widget = forms.HiddenInput()

    umkm_list = UMKM.objects.all()
    return render(request, 'inventory/tambah_produk.html', {
        'form': form,
        'umkm': umkm_list,
        'selected_umkm': selected_umkm,
        'selected_umkm_id': selected_umkm.id if selected_umkm else None,
    })


@login_required
def edit_produk(request, produk_id):
    produk = get_object_or_404(Produk, id=produk_id)
    selected_umkm_id = request.GET.get('umkm_id') or request.POST.get('umkm_id') or produk.umkm_id
    selected_umkm = None
    if selected_umkm_id:
        selected_umkm = get_object_or_404(UMKM, id=selected_umkm_id)
        if produk.umkm_id != selected_umkm.id:
            messages.error(request, "Anda tidak memiliki izin untuk mengubah produk UMKM lain.")
            return redirect('detail_umkm', umkm_id=produk.umkm_id)

    if request.method == 'POST':
        post_data = request.POST.copy()
        post_data['umkm'] = str(produk.umkm_id)
        form = ProdukForm(post_data, instance=produk)
        if form.is_valid():
            form.save()
            if selected_umkm:
                messages.success(request, f"Data produk '{produk.nama_produk}' berhasil diperbarui.")
                return redirect('detail_umkm', umkm_id=selected_umkm.id)
            messages.success(request, f"Data produk '{produk.nama_produk}' berhasil diperbarui.")
            return redirect('data_produk')
        else:
            messages.error(request, "Gagal memperbarui produk. Periksa kembali input.")
    else:
        form = ProdukForm(instance=produk)

    form.fields['umkm'].widget = forms.HiddenInput()
    umkm_list = UMKM.objects.all()
    return render(request, 'inventory/edit_produk.html', {
        'form': form,
        'produk': produk,
        'umkm': umkm_list,
        'selected_umkm': selected_umkm,
        'selected_umkm_id': produk.umkm_id,
    })


@login_required
def hapus_produk(request, produk_id):
    produk = get_object_or_404(Produk, id=produk_id)
    selected_umkm_id = request.GET.get('umkm_id') or request.POST.get('umkm_id')
    if selected_umkm_id:
        if produk.umkm_id != int(selected_umkm_id):
            messages.error(request, "Produk yang dipilih tidak termasuk dalam UMKM yang sedang dibuka.")
            return redirect('data_produk')

    nama = produk.nama_produk
    umkm_id = produk.umkm_id
    produk.delete()
    messages.success(request, f"Produk '{nama}' berhasil dihapus.")
    if selected_umkm_id:
        return redirect('detail_umkm', umkm_id=umkm_id)
    return redirect('data_produk')


# ==================================================
# DATA STOK KANTOR & SEMUA STOK
# ==================================================

@login_required
def data_stok(request):
    query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()

    stok_list = Stok.objects.select_related('produk', 'produk__umkm').all()

    if query:
        stok_list = stok_list.filter(
            Q(produk__kode_produk__icontains=query) |
            Q(produk__nama_produk__icontains=query) |
            Q(produk__umkm__nama__icontains=query) |
            Q(produk__kategori__icontains=query)
        )

    # Filter status aman / menipis / habis
    if status_filter:
        filtered_list = []
        for s in stok_list:
            if status_filter.lower() == s.status.lower():
                filtered_list.append(s)
        stok_list = filtered_list

    return render(request, 'inventory/data_stok.html', {
        'stok': stok_list,
        'query': query,
        'status_filter': status_filter,
    })


@login_required
def edit_stok(request, stok_id):
    stok = get_object_or_404(Stok.objects.select_related('produk'), id=stok_id)

    if request.method == 'POST':
        try:
            stok_kantor_baru = int(request.POST.get('stok_kantor', 0))
            if stok_kantor_baru < 0:
                messages.error(request, "Stok kantor tidak boleh kurang dari 0.")
                return redirect('edit_stok', stok_id=stok.id)

            stok_kantor_lama = stok.stok_kantor
            selisih = stok_kantor_baru - stok_kantor_lama

            with transaction.atomic():
                stok.stok_kantor = stok_kantor_baru
                stok.save()

                if selisih != 0:
                    RiwayatStok.objects.create(
                        produk=stok.produk,
                        jenis_transaksi='PENYESUAIAN',
                        jumlah=selisih,
                        stok_sebelum=stok_kantor_lama,
                        stok_sesudah=stok_kantor_baru,
                        lokasi='Kantor',
                        keterangan=f"Penyesuaian manual stok kantor dari {stok_kantor_lama} ke {stok_kantor_baru}"
                    )

            messages.success(request, f"Stok kantor untuk '{stok.produk.nama_produk}' berhasil diperbarui.")
            return redirect('data_stok')

        except (ValueError, TypeError):
            messages.error(request, "Input stok tidak valid.")

    return render(request, 'inventory/edit_stok.html', {'stok': stok})


@login_required
def riwayat_stok_view(request):
    query = request.GET.get('q', '').strip()
    jenis = request.GET.get('jenis', '').strip()

    riwayat_list = RiwayatStok.objects.select_related('produk').all()

    if query:
        riwayat_list = riwayat_list.filter(
            Q(produk__nama_produk__icontains=query) |
            Q(produk__kode_produk__icontains=query) |
            Q(keterangan__icontains=query)
        )

    if jenis:
        riwayat_list = riwayat_list.filter(jenis_transaksi=jenis)

    return render(request, 'inventory/riwayat_stok.html', {
        'riwayat_list': riwayat_list,
        'query': query,
        'jenis': jenis,
    })


# ==================================================
# KANTOR
# ==================================================

@login_required
def data_kantor(request):
    query = request.GET.get('q', '').strip()
    stok_list = Stok.objects.select_related('produk', 'produk__umkm').all()

    if query:
        stok_list = stok_list.filter(
            Q(produk__kode_produk__icontains=query) |
            Q(produk__nama_produk__icontains=query) |
            Q(produk__umkm__nama__icontains=query) |
            Q(produk__kategori__icontains=query)
        )

    total_kantor = Stok.objects.aggregate(total=Sum('stok_kantor'))['total'] or 0

    return render(request, 'inventory/data_kantor.html', {
        'stok': stok_list,
        'total_kantor': total_kantor,
        'query': query,
    })


# ==================================================
# CHANEL / TOKO
# ==================================================

@login_required
def data_bazar(request):
    query = request.GET.get('q', '').strip()
    chanel_list = Chanel.objects.all()

    if query:
        chanel_list = chanel_list.filter(
            Q(nama_toko__icontains=query) |
            Q(lokasi__icontains=query) |
            Q(keterangan__icontains=query)
        )

    return render(request, 'inventory/data_bazar.html', {
        'chanel': chanel_list,
        'query': query,
    })


@login_required
def chanel_seluruh_bazar(request):
    """
    Rekap otomatis stok dari seluruh Chanel/Toko.
    Menampilkan agregasi stok per produk dari semua toko.
    Read-only, tidak ada input stok di sini.
    """

    chanel_list = Chanel.objects.all()
    stok_chanel_all = StokChanel.objects.select_related(
        'produk', 'produk__umkm'
    ).all()

    produk_stok_map = {}
    for stok in stok_chanel_all:
        produk_id = stok.produk.id
        if produk_id not in produk_stok_map:
            produk_stok_map[produk_id] = {
                'produk': stok.produk,
                'stok_total': 0,
            }
        produk_stok_map[produk_id]['stok_total'] += stok.jumlah

    stok_aggregated = list(produk_stok_map.values())
    stok_aggregated.sort(key=lambda x: x['produk'].nama_produk)

    total_produk = len(stok_aggregated)
    umkm_set = {item['produk'].umkm.id for item in stok_aggregated if item['produk'].umkm}
    total_umkm = len(umkm_set)
    total_stok_all = sum(item['stok_total'] for item in stok_aggregated)

    context = {
        'chanel_list': chanel_list,
        'active_chanel': None,
        'stok': stok_aggregated,
        'total_produk': total_produk,
        'total_umkm': total_umkm,
        'total_stok': total_stok_all,
    }

    return render(
        request,
        "inventory/seluruh_bazar.html",
        context
    )


@login_required
def tambah_chanel(request):
    if request.method == 'POST':
        form = ChanelForm(request.POST)
        if form.is_valid():
            chanel = form.save()
            messages.success(request, f"Chanel '{chanel.nama_toko}' berhasil ditambahkan.")
            return redirect('data_bazar')
        else:
            messages.error(request, "Gagal menambahkan chanel. Pastikan nama toko belum pernah dipakai.")
    else:
        form = ChanelForm()

    return render(request, 'inventory/tambah_chanel.html', {'form': form})


@login_required
def edit_chanel(request, chanel_id):
    chanel = get_object_or_404(Chanel, id=chanel_id)
    if request.method == 'POST':
        form = ChanelForm(request.POST, instance=chanel)
        if form.is_valid():
            form.save()
            messages.success(request, f"Chanel '{chanel.nama_toko}' berhasil diperbarui.")
            return redirect('detail_chanel', chanel_id=chanel.id)
        else:
            messages.error(request, "Gagal memperbarui chanel.")
    else:
        form = ChanelForm(instance=chanel)

    return render(request, 'inventory/edit_chanel.html', {'form': form, 'chanel': chanel})


@login_required
def hapus_chanel(request, chanel_id):
    chanel = get_object_or_404(Chanel, id=chanel_id)
    if request.method == 'POST':
        nama = chanel.nama_toko
        chanel.delete()
        messages.success(request, f"Chanel '{nama}' berhasil dihapus.")
        return redirect('data_bazar')

    return render(request, 'inventory/hapus_chanel.html', {'chanel': chanel})


@login_required
def detail_chanel(request, chanel_id):
    chanel = get_object_or_404(Chanel, id=chanel_id)
    query = request.GET.get('q', '').strip()

    stok_list = StokChanel.objects.filter(chanel=chanel).select_related('produk', 'produk__umkm')

    if query:
        stok_list = stok_list.filter(
            Q(produk__kode_produk__icontains=query) |
            Q(produk__nama_produk__icontains=query) |
            Q(produk__umkm__nama__icontains=query)
        )

    return render(request, 'inventory/detail_chanel.html', {
        'chanel': chanel,
        'stok': stok_list,
        'query': query,
    })


@login_required
def tambah_stok_chanel(request, chanel_id):
    chanel = get_object_or_404(Chanel, id=chanel_id)

    if request.method == 'POST':
        produk_id = request.POST.get('produk')
        jumlah_str = request.POST.get('jumlah')
        sumber_barang = request.POST.get('sumber_barang', 'kantor').strip().lower()
        keterangan_input = request.POST.get('keterangan', '').strip()

        try:
            jumlah = int(jumlah_str)
        except (TypeError, ValueError):
            messages.error(request, "Jumlah stok tidak valid.")
            return redirect('tambah_stok_chanel', chanel_id=chanel.id)

        if jumlah <= 0:
            messages.error(request, "Jumlah stok harus lebih dari 0.")
            return redirect('tambah_stok_chanel', chanel_id=chanel.id)

        produk = get_object_or_404(Produk, id=produk_id)

        with transaction.atomic():
            # 1. Jika sumber dari "Stok Kantor", validasi ketersediaan dan kurangi persediaan kantor secara otomatis
            if sumber_barang == 'kantor':
                stok_kantor_obj, _ = Stok.objects.select_for_update().get_or_create(
                    produk=produk,
                    defaults={'stok_kantor': 0, 'stok_bazar': 0}
                )

                if stok_kantor_obj.stok_kantor < jumlah:
                    messages.error(
                        request,
                        f"Gagal! Stok kantor untuk '{produk.nama_produk}' tidak mencukupi. "
                        f"Tersedia di kantor: {stok_kantor_obj.stok_kantor} unit, diminta: {jumlah} unit."
                    )
                    return redirect('tambah_stok_chanel', chanel_id=chanel.id)

                stok_sebelum_kantor = stok_kantor_obj.stok_kantor
                stok_kantor_obj.stok_kantor -= jumlah
                stok_kantor_obj.save()

                # Catat ke tabel Distribusi agar data alokasi tercatat konsisten
                ket_dist = keterangan_input if keterangan_input else f"Alokasi stok ke {chanel.nama_toko}"
                Distribusi.objects.create(
                    produk=produk,
                    chanel=chanel,
                    jumlah=jumlah,
                    asal='Kantor',
                    tujuan=chanel.nama_toko,
                    keterangan=ket_dist
                )

                # Catat mutasi berkurang di RiwayatStok Kantor
                RiwayatStok.objects.create(
                    produk=produk,
                    jenis_transaksi='DISTRIBUSI',
                    jumlah=-jumlah,
                    stok_sebelum=stok_sebelum_kantor,
                    stok_sesudah=stok_kantor_obj.stok_kantor,
                    lokasi='Kantor',
                    keterangan=f"Pengurangan stok kantor untuk {chanel.nama_toko} ({ket_dist})"
                )

            # 2. Tambahkan stok di Toko/Chanel yang dituju
            stok_chanel, created = StokChanel.objects.select_for_update().get_or_create(
                produk=produk,
                chanel=chanel,
                defaults={'jumlah': 0}
            )
            stok_sebelum_toko = stok_chanel.jumlah
            stok_chanel.jumlah += jumlah
            stok_chanel.save()

            # Catat mutasi bertambah di RiwayatStok Toko
            sumber_nama = "Stok Kantor" if sumber_barang == 'kantor' else "Non-Kantor (Langsung)"
            RiwayatStok.objects.create(
                produk=produk,
                jenis_transaksi='PENYESUAIAN',
                jumlah=jumlah,
                stok_sebelum=stok_sebelum_toko,
                stok_sesudah=stok_chanel.jumlah,
                lokasi=f"Chanel: {chanel.nama_toko}",
                keterangan=f"Penambahan stok di {chanel.nama_toko} (Sumber: {sumber_nama})"
            )

        pesan_potong = " (stok kantor otomatis dipotong)" if sumber_barang == 'kantor' else ""
        messages.success(request, f"Berhasil menambahkan {jumlah} stok '{produk.nama_produk}' ke {chanel.nama_toko}{pesan_potong}.")
        return redirect('detail_chanel', chanel_id=chanel.id)

    produk_list = Produk.objects.select_related('stok', 'umkm').all()
    return render(request, 'inventory/tambah_stok_chanel.html', {
        'chanel': chanel,
        'produk': produk_list,
    })


@login_required
def edit_stok_chanel(request, stok_id):
    stok_chanel = get_object_or_404(
        StokChanel.objects.select_related('produk', 'chanel'),
        id=stok_id
    )

    if request.method == 'POST':
        try:
            jumlah_baru = int(request.POST.get('jumlah', 0))
        except (TypeError, ValueError):
            messages.error(request, "Jumlah stok tidak valid.")
            return redirect('edit_stok_chanel', stok_id=stok_chanel.id)

        if jumlah_baru < 0:
            messages.error(request, "Jumlah stok tidak boleh kurang dari 0.")
            return redirect('edit_stok_chanel', stok_id=stok_chanel.id)

        stok_lama = stok_chanel.jumlah
        selisih = jumlah_baru - stok_lama

        with transaction.atomic():
            stok_chanel.jumlah = jumlah_baru
            stok_chanel.save()

            if selisih != 0:
                RiwayatStok.objects.create(
                    produk=stok_chanel.produk,
                    jenis_transaksi='PENYESUAIAN',
                    jumlah=selisih,
                    stok_sebelum=stok_lama,
                    stok_sesudah=jumlah_baru,
                    lokasi=f"Chanel: {stok_chanel.chanel.nama_toko}",
                    keterangan=f"Penyesuaian stok di {stok_chanel.chanel.nama_toko} dari {stok_lama} ke {jumlah_baru}"
                )

        messages.success(request, f"Stok {stok_chanel.produk.nama_produk} di {stok_chanel.chanel.nama_toko} berhasil diperbarui.")
        return redirect('detail_chanel', chanel_id=stok_chanel.chanel.id)

    return render(request, 'inventory/edit_stok_chanel.html', {'stok': stok_chanel})


@login_required
def hapus_stok_chanel(request, stok_id):
    stok_chanel = get_object_or_404(StokChanel, id=stok_id)
    chanel_id = stok_chanel.chanel.id
    nama_produk = stok_chanel.produk.nama_produk
    stok_chanel.delete()
    messages.success(request, f"Produk '{nama_produk}' dihapus dari daftar stok toko.")
    return redirect('detail_chanel', chanel_id=chanel_id)


# ==================================================
# DISTRIBUSI (KANTOR -> CHANEL/TOKO)
# ==================================================

@login_required
def data_distribusi(request):
    query = request.GET.get('q', '').strip()
    distribusi_list = Distribusi.objects.select_related('produk', 'chanel').order_by('-tanggal')

    if query:
        distribusi_list = distribusi_list.filter(
            Q(produk__kode_produk__icontains=query) |
            Q(produk__nama_produk__icontains=query) |
            Q(chanel__nama_toko__icontains=query) |
            Q(tujuan__icontains=query) |
            Q(keterangan__icontains=query)
        )

    return render(request, 'inventory/data_distribusi.html', {
        'distribusi': distribusi_list,
        'query': query,
    })


@login_required
def tambah_distribusi(request):

    if request.method == 'POST':

        # Mengambil data dari form
        produk_id = request.POST.get('produk')

        # Lokasi asal selalu Rumah BUMN Pusat
        asal_val = 'Kantor'
        asal_nama = 'Kantor'

        # Lokasi tujuan tetap dipilih pengguna
        tujuan_val = request.POST.get('tujuan', '').strip()

        # Kompatibilitas dengan form lama
        if not tujuan_val and request.POST.get('chanel'):
            tujuan_val = f"chanel_{request.POST.get('chanel')}"

        jumlah_str = request.POST.get('jumlah')
        keterangan = request.POST.get('keterangan', '').strip()

        # Validasi jumlah
        try:
            jumlah = int(jumlah_str)
        except (TypeError, ValueError):
            messages.error(request, "Jumlah distribusi tidak valid.")
            return redirect('tambah_distribusi')

        if jumlah <= 0:
            messages.error(
                request,
                "Jumlah distribusi harus lebih dari 0."
            )
            return redirect('tambah_distribusi')

        # Validasi lokasi tujuan
        if not tujuan_val:
            messages.error(
                request,
                "Silakan pilih lokasi tujuan distribusi."
            )
            return redirect('tambah_distribusi')

        if tujuan_val.lower() == 'kantor':
            messages.error(
                request,
                "Lokasi tujuan tidak boleh Rumah BUMN Pusat."
            )
            return redirect('tambah_distribusi')

        # Mengambil produk
        produk = get_object_or_404(Produk, id=produk_id)

        # Menentukan toko tujuan
        chanel_tujuan = None

        if tujuan_val.startswith('chanel_'):

            try:
                ch_id = int(tujuan_val.split('_', 1)[1])
            except (ValueError, IndexError):
                messages.error(
                    request,
                    "Lokasi tujuan tidak valid."
                )
                return redirect('tambah_distribusi')

            chanel_tujuan = get_object_or_404(
                Chanel,
                id=ch_id
            )

        else:
            chanel_tujuan = Chanel.objects.filter(
                nama_toko__iexact=tujuan_val
            ).first()

            if not chanel_tujuan:
                messages.error(
                    request,
                    "Toko tujuan tidak ditemukan."
                )
                return redirect('tambah_distribusi')

        tujuan_nama = chanel_tujuan.nama_toko

        # PROSES DISTRIBUSI
        with transaction.atomic():

            # 1. Mengambil stok Rumah BUMN Pusat
            stok_kantor, created = (
                Stok.objects.select_for_update().get_or_create(
                    produk=produk,
                    defaults={
                        'stok_kantor': 0,
                        'stok_bazar': 0
                    }
                )
            )

            # 2. Memeriksa stok kantor
            if stok_kantor.stok_kantor < jumlah:

                messages.error(
                    request,
                    f"Stok Rumah BUMN Pusat tidak mencukupi! "
                    f"Tersedia {stok_kantor.stok_kantor} unit."
                )

                return redirect('tambah_distribusi')

            # 3. Mengurangi stok kantor pusat
            stok_sebelum_asal = stok_kantor.stok_kantor

            stok_kantor.stok_kantor -= jumlah
            stok_kantor.save()

            stok_sesudah_asal = stok_kantor.stok_kantor

            # 4. Mengambil stok toko tujuan
            stok_tujuan, created = (
                StokChanel.objects.select_for_update().get_or_create(
                    produk=produk,
                    chanel=chanel_tujuan,
                    defaults={'jumlah': 0}
                )
            )

            # 5. Menambahkan stok toko tujuan
            stok_sebelum_tujuan = stok_tujuan.jumlah

            stok_tujuan.jumlah += jumlah
            stok_tujuan.save()

            stok_sesudah_tujuan = stok_tujuan.jumlah

            # 6. Menyimpan data distribusi
            Distribusi.objects.create(
                produk=produk,
                chanel=chanel_tujuan,
                jumlah=jumlah,
                asal=asal_nama,
                tujuan=tujuan_nama,
                keterangan=keterangan
            )

            # 7. Mencatat riwayat stok keluar
            ket_tambahan = (
                f" ({keterangan})" if keterangan else ""
            )

            RiwayatStok.objects.create(
                produk=produk,
                jenis_transaksi='DISTRIBUSI',
                jumlah=-jumlah,
                stok_sebelum=stok_sebelum_asal,
                stok_sesudah=stok_kantor.stok_kantor,
                lokasi='Kantor',
                keterangan=(
                    f"Distribusi keluar ke "
                    f"{tujuan_nama}{ket_tambahan}"
                )
            )

            # 8. Mencatat riwayat stok masuk
            RiwayatStok.objects.create(
                produk=produk,
                jenis_transaksi='PENYESUAIAN',
                jumlah=jumlah,
                stok_sebelum=stok_sebelum_tujuan,
                stok_sesudah=stok_tujuan.jumlah,
                lokasi=f"Chanel: {tujuan_nama}",
                keterangan=(
                    f"Distribusi masuk dari "
                    f"Rumah BUMN Pusat{ket_tambahan}"
                )
            )

        # Pesan berhasil
        messages.success(
            request,
            f"Distribusi {jumlah} item "
            f"'{produk.nama_produk}' "
            f"dari Rumah BUMN Pusat "
            f"ke {tujuan_nama} berhasil dilakukan."
        )

        return redirect('data_distribusi')

    # DATA UNTUK MENAMPILKAN FORM

    produk_list = (
        Produk.objects.select_related(
            'stok',
            'umkm'
        ).prefetch_related(
            'stok_chanel'
        ).all()
    )

    # Mengambil daftar toko aktif
    chanel_list = Chanel.objects.all()

    # Membuat matriks stok
    stok_matrix = {}

    for p in produk_list:

        stok_matrix[p.id] = {
            'Kantor': p.stok_kantor
        }

        for sc in p.stok_chanel.all():

            stok_matrix[p.id][
                f"chanel_{sc.chanel_id}"
            ] = sc.jumlah

    # Menampilkan halaman tambah distribusi
    return render(
        request,
        'inventory/tambah_distribusi.html',
        {
            'produk': produk_list,
            'chanel': chanel_list,
            'stok_matrix_json': json.dumps(stok_matrix),
        }
    )


@login_required
def edit_distribusi(request, distribusi_id):
    distribusi = get_object_or_404(
        Distribusi.objects.select_related('produk', 'chanel'),
        id=distribusi_id
    )

    if request.method == 'POST':
        try:
            jumlah_baru = int(request.POST.get('jumlah', 0))
        except (TypeError, ValueError):
            messages.error(request, "Jumlah tidak valid.")
            return render(request, 'inventory/edit_distribusi.html', {'distribusi': distribusi})

        if jumlah_baru <= 0:
            messages.error(request, "Jumlah distribusi harus lebih dari 0.")
            return render(request, 'inventory/edit_distribusi.html', {'distribusi': distribusi})

        keterangan = request.POST.get('keterangan', '').strip()
        jumlah_lama = distribusi.jumlah
        selisih = jumlah_baru - jumlah_lama  # positif: butuh tambahan dari kantor; negatif: kelebihan, kembalikan ke kantor

        with transaction.atomic():
            stok_kantor = Stok.objects.select_for_update().get(produk=distribusi.produk)

            if selisih > 0:
                # Periksa apakah kantor punya cukup stok untuk penambahan
                if stok_kantor.stok_kantor < selisih:
                    messages.error(request, f"Stok kantor tidak mencukupi untuk penambahan {selisih} unit!")
                    return render(request, 'inventory/edit_distribusi.html', {'distribusi': distribusi})
                stok_kantor.stok_kantor -= selisih
            elif selisih < 0:
                # Kembalikan kelebihan ke kantor
                stok_kantor.stok_kantor += abs(selisih)

            stok_kantor.save()

            # Sesuaikan stok chanel tujuan
            if distribusi.chanel:
                stok_c = StokChanel.objects.select_for_update().filter(
                    produk=distribusi.produk,
                    chanel=distribusi.chanel
                ).first()
                if stok_c:
                    stok_c.jumlah = max(0, stok_c.jumlah + selisih)
                    stok_c.save()

            distribusi.jumlah = jumlah_baru
            distribusi.keterangan = keterangan
            distribusi.save()

            RiwayatStok.objects.create(
                produk=distribusi.produk,
                jenis_transaksi='PENYESUAIAN',
                jumlah=-selisih,
                stok_sebelum=stok_kantor.stok_kantor + selisih,
                stok_sesudah=stok_kantor.stok_kantor,
                lokasi='Kantor',
                keterangan=f"Edit distribusi #{distribusi.id} dari {jumlah_lama} menjadi {jumlah_baru}"
            )

        messages.success(request, "Data distribusi dan saldo stok berhasil disesuaikan.")
        return redirect('data_distribusi')

    return render(request, 'inventory/edit_distribusi.html', {'distribusi': distribusi})


@login_required
def hapus_distribusi(request, distribusi_id):
    distribusi = get_object_or_404(
        Distribusi.objects.select_related('produk', 'chanel'),
        id=distribusi_id
    )

    with transaction.atomic():
        # 1. Kembalikan stok ke lokasi ASAL
        if distribusi.asal == 'Kantor':
            stok_kantor = Stok.objects.select_for_update().get(produk=distribusi.produk)
            stok_sebelum_asal = stok_kantor.stok_kantor
            stok_kantor.stok_kantor += distribusi.jumlah
            stok_kantor.save()
            stok_sesudah_asal = stok_kantor.stok_kantor
        else:
            ch_asal = Chanel.objects.filter(nama_toko=distribusi.asal).first()
            if ch_asal:
                stok_c_asal, _ = StokChanel.objects.select_for_update().get_or_create(
                    produk=distribusi.produk,
                    chanel=ch_asal,
                    defaults={'jumlah': 0}
                )
                stok_sebelum_asal = stok_c_asal.jumlah
                stok_c_asal.jumlah += distribusi.jumlah
                stok_c_asal.save()
                stok_sesudah_asal = stok_c_asal.jumlah
            else:
                stok_sebelum_asal = 0
                stok_sesudah_asal = 0

        # 2. Tarik kembali stok dari lokasi TUJUAN
        if distribusi.tujuan == 'Kantor':
            stok_kantor = Stok.objects.select_for_update().get(produk=distribusi.produk)
            stok_kantor.stok_kantor = max(0, stok_kantor.stok_kantor - distribusi.jumlah)
            stok_kantor.save()
        else:
            ch_tujuan = distribusi.chanel or Chanel.objects.filter(nama_toko=distribusi.tujuan).first()
            if ch_tujuan:
                stok_c_tujuan = StokChanel.objects.select_for_update().filter(
                    produk=distribusi.produk,
                    chanel=ch_tujuan
                ).first()
                if stok_c_tujuan:
                    stok_c_tujuan.jumlah = max(0, stok_c_tujuan.jumlah - distribusi.jumlah)
                    stok_c_tujuan.save()

        RiwayatStok.objects.create(
            produk=distribusi.produk,
            jenis_transaksi='KEMBALI_DISTRIBUSI',
            jumlah=distribusi.jumlah,
            stok_sebelum=stok_sebelum_asal,
            stok_sesudah=stok_sesudah_asal,
            lokasi=distribusi.asal,
            keterangan=f"Pembatalan distribusi #{distribusi.id} ({distribusi.jumlah} unit dikembalikan ke {distribusi.asal})"
        )

        distribusi.delete()

    messages.success(request, f"Distribusi dibatalkan dan stok dikembalikan ke {distribusi.asal} secara aman.")
    return redirect('data_distribusi')


# ==================================================
# BARANG MASUK
# ==================================================

@login_required
def data_barang_masuk(request):
    query = request.GET.get('q', '').strip()
    data = BarangMasuk.objects.select_related('produk').order_by('-tanggal')

    if query:
        data = data.filter(
            Q(produk__kode_produk__icontains=query) |
            Q(produk__nama_produk__icontains=query) |
            Q(asal__icontains=query) |
            Q(keterangan__icontains=query)
        )

    return render(request, 'inventory/data_barang_masuk.html', {
        'barang_masuk': data,
        'query': query,
    })


@login_required
def tambah_barang_masuk(request):
    if request.method == 'POST':
        produk_id = request.POST.get('produk')
        jumlah_str = request.POST.get('jumlah')
        asal = request.POST.get('asal', '').strip()
        keterangan = request.POST.get('keterangan', '').strip()

        try:
            jumlah = int(jumlah_str)
        except (TypeError, ValueError):
            messages.error(request, "Jumlah barang tidak valid.")
            return redirect('tambah_barang_masuk')

        if jumlah <= 0:
            messages.error(request, "Jumlah barang masuk harus lebih dari 0.")
            return redirect('tambah_barang_masuk')

        produk = get_object_or_404(Produk, id=produk_id)

        with transaction.atomic():
            BarangMasuk.objects.create(
                produk=produk,
                jumlah=jumlah,
                asal=asal,
                tujuan='Kantor',
                keterangan=keterangan
            )

            stok, _ = Stok.objects.select_for_update().get_or_create(
                produk=produk,
                defaults={'stok_kantor': 0, 'stok_bazar': 0}
            )
            stok_sebelum = stok.stok_kantor
            stok.stok_kantor += jumlah
            stok.save()

            RiwayatStok.objects.create(
                produk=produk,
                jenis_transaksi='MASUK',
                jumlah=jumlah,
                stok_sebelum=stok_sebelum,
                stok_sesudah=stok.stok_kantor,
                lokasi='Kantor',
                keterangan=f"Penerimaan barang dari {asal}" if asal else "Barang masuk ke kantor"
            )

        messages.success(request, f"Berhasil menambahkan {jumlah} stok untuk '{produk.nama_produk}'.")
        return redirect('data_barang_masuk')

    produk_list = Produk.objects.all()
    return render(request, 'inventory/tambah_barang_masuk.html', {'produk': produk_list})


# ==================================================
# BARANG KELUAR
# ==================================================

@login_required
def data_barang_keluar(request):
    query = request.GET.get('q', '').strip()
    data = BarangKeluar.objects.select_related('produk').order_by('-tanggal')

    if query:
        data = data.filter(
            Q(produk__kode_produk__icontains=query) |
            Q(produk__nama_produk__icontains=query) |
            Q(tujuan__icontains=query) |
            Q(keterangan__icontains=query)
        )

    return render(request, 'inventory/data_barang_keluar.html', {
        'barang_keluar': data,
        'query': query,
    })


@login_required
def tambah_barang_keluar(request):
    if request.method == 'POST':
        produk_id = request.POST.get('produk')
        jumlah_str = request.POST.get('jumlah')
        tujuan = request.POST.get('tujuan', '').strip()
        keterangan = request.POST.get('keterangan', '').strip()

        try:
            jumlah = int(jumlah_str)
        except (TypeError, ValueError):
            messages.error(request, "Jumlah tidak valid.")
            return redirect('tambah_barang_keluar')

        if jumlah <= 0:
            messages.error(request, "Jumlah barang keluar harus lebih dari 0.")
            return redirect('tambah_barang_keluar')

        produk = get_object_or_404(Produk, id=produk_id)

        with transaction.atomic():
            stok, _ = Stok.objects.select_for_update().get_or_create(
                produk=produk,
                defaults={'stok_kantor': 0, 'stok_bazar': 0}
            )

            if stok.stok_kantor < jumlah:
                messages.error(
                    request,
                    f"Stok kantor tidak mencukupi! Tersedia: {stok.stok_kantor}, dikeluarkan: {jumlah}."
                )
                return redirect('tambah_barang_keluar')

            stok_sebelum = stok.stok_kantor
            stok.stok_kantor -= jumlah
            stok.save()

            BarangKeluar.objects.create(
                produk=produk,
                jumlah=jumlah,
                asal='Kantor',
                tujuan=tujuan,
                keterangan=keterangan
            )

            RiwayatStok.objects.create(
                produk=produk,
                jenis_transaksi='KELUAR',
                jumlah=-jumlah,
                stok_sebelum=stok_sebelum,
                stok_sesudah=stok.stok_kantor,
                lokasi='Kantor',
                keterangan=f"Pengeluaran ke {tujuan}" if tujuan else "Pengeluaran barang dari kantor"
            )

        messages.success(request, f"Pengeluaran {jumlah} item '{produk.nama_produk}' berhasil dicatat.")
        return redirect('data_barang_keluar')

    produk_list = Produk.objects.all()
    return render(request, 'inventory/tambah_barang_keluar.html', {'produk': produk_list})


# ==================================================
# LAPORAN INVENTORI OTOMATIS
# ==================================================

from datetime import date, timedelta


def _get_date_range(request):
    """
    Hitung rentang tanggal berdasarkan parameter GET.
    Kembalikan (start_date, end_date, periode_label) sebagai objek date.
    """
    today = date.today()
    periode_preset = request.GET.get('periode_preset', '').strip()
    start_str = request.GET.get('start_date', '').strip()
    end_str = request.GET.get('end_date', '').strip()

    if periode_preset == 'today':
        return today, today, 'Hari Ini'
    elif periode_preset == 'yesterday':
        d = today - timedelta(days=1)
        return d, d, 'Kemarin'
    elif periode_preset == 'last7':
        return today - timedelta(days=6), today, '7 Hari Terakhir'
    elif periode_preset == 'last30':
        return today - timedelta(days=29), today, '30 Hari Terakhir'
    elif periode_preset == 'this_month':
        return today.replace(day=1), today, 'Bulan Ini'
    elif periode_preset == 'last_month':
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        first_prev = last_prev.replace(day=1)
        return first_prev, last_prev, 'Bulan Sebelumnya'
    elif periode_preset == 'this_year':
        return today.replace(month=1, day=1), today, 'Tahun Ini'
    else:
        # Rentang khusus
        sd = None
        ed = None
        try:
            if start_str:
                sd = datetime.strptime(start_str, '%Y-%m-%d').date()
        except ValueError:
            pass
        try:
            if end_str:
                ed = datetime.strptime(end_str, '%Y-%m-%d').date()
        except ValueError:
            pass

        if sd and ed and sd > ed:
            ed = sd

        if sd or ed:
            label_parts = []
            if sd:
                label_parts.append(sd.strftime('%d/%m/%Y'))
            else:
                label_parts.append('Awal')
            label_parts.append('s/d')
            if ed:
                label_parts.append(ed.strftime('%d/%m/%Y'))
            else:
                label_parts.append('Sekarang')
            return sd, ed, ' '.join(label_parts)
        else:
            return None, None, 'Semua Periode'


def _apply_date_filter(queryset, start_date, end_date, field='tanggal'):
    if start_date:
        queryset = queryset.filter(**{f'{field}__date__gte': start_date})
    if end_date:
        queryset = queryset.filter(**{f'{field}__date__lte': end_date})
    return queryset


@login_required
def laporan(request):
    """
    View utama laporan inventori otomatis dengan multi-jenis laporan dan filter lengkap.
    """
    jenis_laporan = request.GET.get('jenis_laporan', 'stok_saat_ini').strip()
    produk_id = request.GET.get('produk_id', '').strip()
    kategori_filter = request.GET.get('kategori', '').strip()
    chanel_id = request.GET.get('chanel_id', '').strip()
    lokasi_filter = request.GET.get('lokasi', '').strip()
    show_report = request.GET.get('show_report', '0')

    start_date, end_date, periode_label = _get_date_range(request)

    produk_options = Produk.objects.select_related('umkm').order_by('nama_produk')
    chanel_options = Chanel.objects.filter(aktif=True).order_by('nama_toko')
    kategori_list = [k for k in Produk.objects.values_list('kategori', flat=True).distinct() if k]
    kategori_list.sort()

    selected_produk = None
    if produk_id:
        try:
            selected_produk = Produk.objects.get(id=produk_id)
        except (Produk.DoesNotExist, ValueError):
            produk_id = ''

    selected_chanel = None
    if chanel_id:
        try:
            selected_chanel = Chanel.objects.get(id=chanel_id)
        except (Chanel.DoesNotExist, ValueError):
            chanel_id = ''

    laporan_data = {}
    ringkasan = {}
    jenis_laporan_labels = {
        'stok_saat_ini': 'Laporan Stok Saat Ini',
        'barang_masuk': 'Laporan Barang Masuk',
        'barang_keluar': 'Laporan Barang Keluar',
        'distribusi': 'Laporan Distribusi',
        'pergerakan_stok': 'Laporan Pergerakan Stok',
        'stok_menipis': 'Laporan Stok Menipis',
        'rekapitulasi': 'Laporan Rekapitulasi per Produk',
    }

    if show_report == '1' or request.GET.get('jenis_laporan'):
        # 1. LAPORAN STOK SAAT INI
        if jenis_laporan == 'stok_saat_ini':
            qs = Stok.objects.select_related('produk', 'produk__umkm').all()
            if produk_id:
                qs = qs.filter(produk_id=produk_id)
            if kategori_filter:
                qs = qs.filter(produk__kategori__iexact=kategori_filter)

            rows = []
            total_stok_kantor = 0
            total_stok_chanel = 0
            produk_menipis = 0
            for s in qs:
                sc = s.stok_chanel
                tot = s.stok_kantor + sc
                status = s.produk.status_stok
                rows.append({
                    'kode_produk': s.produk.kode_produk,
                    'nama_produk': s.produk.nama_produk,
                    'kategori': s.produk.kategori or '-',
                    'umkm': s.produk.umkm.nama if s.produk.umkm else '-',
                    'stok_kantor': s.stok_kantor,
                    'stok_bazar': sc,
                    'total_stok': tot,
                    'stok_minimum': s.produk.stok_minimum,
                    'status': status,
                })
                total_stok_kantor += s.stok_kantor
                total_stok_chanel += sc
                if status in ['menipis', 'habis']:
                    produk_menipis += 1

            laporan_data['rows'] = rows
            ringkasan = {
                'jumlah_produk': len(rows),
                'total_stok_kantor': total_stok_kantor,
                'total_stok_bazar': total_stok_chanel,
                'total_stok': total_stok_kantor + total_stok_chanel,
                'produk_menipis': produk_menipis,
            }

        # 2. LAPORAN BARANG MASUK
        elif jenis_laporan == 'barang_masuk':
            qs = BarangMasuk.objects.select_related('produk', 'produk__umkm').order_by('-tanggal')
            if produk_id:
                qs = qs.filter(produk_id=produk_id)
            if kategori_filter:
                qs = qs.filter(produk__kategori__iexact=kategori_filter)
            qs = _apply_date_filter(qs, start_date, end_date)

            rows = []
            total_masuk = 0
            for bm in qs:
                rows.append({
                    'tanggal': bm.tanggal,
                    'kode_produk': bm.produk.kode_produk,
                    'nama_produk': bm.produk.nama_produk,
                    'jumlah': bm.jumlah,
                    'asal': bm.asal or '-',
                    'tujuan': bm.tujuan or '-',
                    'keterangan': bm.keterangan or '-',
                })
                total_masuk += bm.jumlah

            laporan_data['rows'] = rows
            ringkasan = {
                'jumlah_transaksi': len(rows),
                'total_masuk': total_masuk,
            }

        # 3. LAPORAN BARANG KELUAR
        elif jenis_laporan == 'barang_keluar':
            qs = BarangKeluar.objects.select_related('produk', 'produk__umkm').order_by('-tanggal')
            if produk_id:
                qs = qs.filter(produk_id=produk_id)
            if kategori_filter:
                qs = qs.filter(produk__kategori__iexact=kategori_filter)
            qs = _apply_date_filter(qs, start_date, end_date)

            rows = []
            total_keluar = 0
            for bk in qs:
                rows.append({
                    'tanggal': bk.tanggal,
                    'kode_produk': bk.produk.kode_produk,
                    'nama_produk': bk.produk.nama_produk,
                    'jumlah': bk.jumlah,
                    'asal': bk.asal or '-',
                    'tujuan': bk.tujuan or '-',
                    'keterangan': bk.keterangan or '-',
                })
                total_keluar += bk.jumlah

            laporan_data['rows'] = rows
            ringkasan = {
                'jumlah_transaksi': len(rows),
                'total_keluar': total_keluar,
            }

        # 4. LAPORAN DISTRIBUSI
        elif jenis_laporan == 'distribusi':
            qs = Distribusi.objects.select_related('produk', 'produk__umkm', 'chanel').order_by('-tanggal')
            if produk_id:
                qs = qs.filter(produk_id=produk_id)
            if kategori_filter:
                qs = qs.filter(produk__kategori__iexact=kategori_filter)
            if chanel_id:
                qs = qs.filter(chanel_id=chanel_id)
            qs = _apply_date_filter(qs, start_date, end_date)

            rows = []
            total_distribusi = 0
            for d in qs:
                tujuan_str = d.chanel.nama_toko if d.chanel else (d.tujuan or '-')
                rows.append({
                    'tanggal': d.tanggal,
                    'kode_produk': d.produk.kode_produk,
                    'nama_produk': d.produk.nama_produk,
                    'asal': d.asal or '-',
                    'tujuan': tujuan_str,
                    'chanel': d.chanel.nama_toko if d.chanel else '-',
                    'jumlah': d.jumlah,
                    'keterangan': d.keterangan or '-',
                })
                total_distribusi += d.jumlah

            laporan_data['rows'] = rows
            ringkasan = {
                'jumlah_transaksi': len(rows),
                'total_distribusi': total_distribusi,
            }

        # 5. LAPORAN PERGERAKAN STOK
        elif jenis_laporan == 'pergerakan_stok':
            produk_qs = Produk.objects.select_related('umkm').all()
            if produk_id:
                produk_qs = produk_qs.filter(id=produk_id)
            if kategori_filter:
                produk_qs = produk_qs.filter(kategori__iexact=kategori_filter)

            rows = []
            grand_masuk = 0
            grand_keluar = 0
            grand_distribusi = 0

            for p in produk_qs:
                try:
                    stok_obj = p.stok
                    stok_akhir_kantor = stok_obj.stok_kantor
                except Stok.DoesNotExist:
                    stok_akhir_kantor = 0

                masuk_qs = _apply_date_filter(BarangMasuk.objects.filter(produk=p), start_date, end_date)
                keluar_qs = _apply_date_filter(BarangKeluar.objects.filter(produk=p), start_date, end_date)
                dist_qs = _apply_date_filter(Distribusi.objects.filter(produk=p), start_date, end_date)
                penyesuaian_qs = _apply_date_filter(RiwayatStok.objects.filter(produk=p, jenis_transaksi='PENYESUAIAN'), start_date, end_date)

                total_masuk = masuk_qs.aggregate(t=Sum('jumlah'))['t'] or 0
                total_keluar = keluar_qs.aggregate(t=Sum('jumlah'))['t'] or 0
                total_dist = dist_qs.aggregate(t=Sum('jumlah'))['t'] or 0
                total_penyesuaian = penyesuaian_qs.aggregate(t=Sum('jumlah'))['t'] or 0

                stok_awal = stok_akhir_kantor - total_masuk + total_keluar + total_dist - total_penyesuaian

                if total_masuk > 0 or total_keluar > 0 or total_dist > 0 or total_penyesuaian != 0 or produk_id:
                    rows.append({
                        'kode_produk': p.kode_produk,
                        'nama_produk': p.nama_produk,
                        'kategori': p.kategori or '-',
                        'stok_awal': max(stok_awal, 0),
                        'total_masuk': total_masuk,
                        'total_keluar': total_keluar,
                        'total_distribusi': total_dist,
                        'penyesuaian': total_penyesuaian,
                        'stok_akhir': stok_akhir_kantor,
                    })
                    grand_masuk += total_masuk
                    grand_keluar += total_keluar
                    grand_distribusi += total_dist

            laporan_data['rows'] = rows
            ringkasan = {
                'jumlah_produk': len(rows),
                'grand_masuk': grand_masuk,
                'grand_keluar': grand_keluar,
                'grand_distribusi': grand_distribusi,
            }

        # 6. LAPORAN STOK MENIPIS
        elif jenis_laporan == 'stok_menipis':
            qs = Stok.objects.select_related('produk', 'produk__umkm').all()
            if produk_id:
                qs = qs.filter(produk_id=produk_id)
            if kategori_filter:
                qs = qs.filter(produk__kategori__iexact=kategori_filter)

            rows = []
            for s in qs:
                sc = s.stok_chanel
                tot = s.stok_kantor + sc
                min_stok = s.produk.stok_minimum
                if tot <= min_stok:
                    rows.append({
                        'kode_produk': s.produk.kode_produk,
                        'nama_produk': s.produk.nama_produk,
                        'kategori': s.produk.kategori or '-',
                        'umkm': s.produk.umkm.nama if s.produk.umkm else '-',
                        'stok_saat_ini': tot,
                        'stok_kantor': s.stok_kantor,
                        'stok_bazar': sc,
                        'stok_minimum': min_stok,
                        'kekurangan': max(min_stok - tot, 0),
                        'status': 'Habis' if tot <= 0 else 'Menipis',
                    })

            laporan_data['rows'] = rows
            ringkasan = {
                'jumlah_produk_menipis': len(rows),
            }

        # 7. LAPORAN REKAPITULASI PER PRODUK
        elif jenis_laporan == 'rekapitulasi':
            produk_qs = Produk.objects.select_related('umkm').all()
            if produk_id:
                produk_qs = produk_qs.filter(id=produk_id)
            if kategori_filter:
                produk_qs = produk_qs.filter(kategori__iexact=kategori_filter)

            rows = []
            for p in produk_qs:
                masuk_qs = _apply_date_filter(BarangMasuk.objects.filter(produk=p), start_date, end_date)
                keluar_qs = _apply_date_filter(BarangKeluar.objects.filter(produk=p), start_date, end_date)
                dist_qs = _apply_date_filter(Distribusi.objects.filter(produk=p), start_date, end_date)

                total_masuk = masuk_qs.aggregate(t=Sum('jumlah'))['t'] or 0
                total_keluar = keluar_qs.aggregate(t=Sum('jumlah'))['t'] or 0
                total_dist = dist_qs.aggregate(t=Sum('jumlah'))['t'] or 0
                jml_transaksi = masuk_qs.count() + keluar_qs.count() + dist_qs.count()

                try:
                    stok_obj = p.stok
                    stok_kantor = stok_obj.stok_kantor
                    stok_bazar = stok_obj.stok_chanel
                except Stok.DoesNotExist:
                    stok_kantor = 0
                    stok_bazar = 0

                if jml_transaksi > 0 or produk_id:
                    rows.append({
                        'kode_produk': p.kode_produk,
                        'nama_produk': p.nama_produk,
                        'kategori': p.kategori or '-',
                        'umkm': p.umkm.nama if p.umkm else '-',
                        'jumlah_transaksi': jml_transaksi,
                        'total_masuk': total_masuk,
                        'total_keluar': total_keluar,
                        'total_distribusi': total_dist,
                        'stok_kantor': stok_kantor,
                        'stok_bazar': stok_bazar,
                        'stok_total': stok_kantor + stok_bazar,
                    })

            laporan_data['rows'] = rows
            ringkasan = {
                'jumlah_produk': len(rows),
                'grand_masuk': sum(r['total_masuk'] for r in rows),
                'grand_keluar': sum(r['total_keluar'] for r in rows),
                'grand_distribusi': sum(r['total_distribusi'] for r in rows),
            }

    # Data untuk grafik pergerakan stok
    grafik_data = {}
    if show_report == '1' or request.GET.get('jenis_laporan'):
        if jenis_laporan in ['barang_masuk', 'barang_keluar', 'distribusi', 'pergerakan_stok', 'rekapitulasi']:
            from django.db.models.functions import TruncDate
            masuk_qs = BarangMasuk.objects.all()
            keluar_qs = BarangKeluar.objects.all()
            dist_qs = Distribusi.objects.all()

            if produk_id:
                masuk_qs = masuk_qs.filter(produk_id=produk_id)
                keluar_qs = keluar_qs.filter(produk_id=produk_id)
                dist_qs = dist_qs.filter(produk_id=produk_id)
            if kategori_filter:
                masuk_qs = masuk_qs.filter(produk__kategori__iexact=kategori_filter)
                keluar_qs = keluar_qs.filter(produk__kategori__iexact=kategori_filter)
                dist_qs = dist_qs.filter(produk__kategori__iexact=kategori_filter)

            masuk_qs = _apply_date_filter(masuk_qs, start_date, end_date)
            keluar_qs = _apply_date_filter(keluar_qs, start_date, end_date)
            dist_qs = _apply_date_filter(dist_qs, start_date, end_date)

            masuk_by_date = {
                row['k']: row['t']
                for row in masuk_qs.annotate(k=TruncDate('tanggal')).values('k').annotate(t=Sum('jumlah'))
            }
            keluar_by_date = {
                row['k']: row['t']
                for row in keluar_qs.annotate(k=TruncDate('tanggal')).values('k').annotate(t=Sum('jumlah'))
            }
            dist_by_date = {
                row['k']: row['t']
                for row in dist_qs.annotate(k=TruncDate('tanggal')).values('k').annotate(t=Sum('jumlah'))
            }

            all_dates = sorted(set(list(masuk_by_date.keys()) + list(keluar_by_date.keys()) + list(dist_by_date.keys())))
            grafik_data = {
                'labels': [d.strftime('%d/%m/%Y') for d in all_dates if d],
                'masuk': [masuk_by_date.get(d, 0) for d in all_dates if d],
                'keluar': [keluar_by_date.get(d, 0) for d in all_dates if d],
                'distribusi': [dist_by_date.get(d, 0) for d in all_dates if d],
            }

    import json as _json
    context = {
        'produk_options': produk_options,
        'chanel_options': chanel_options,
        'kategori_list': kategori_list,
        'jenis_laporan': jenis_laporan,
        'jenis_laporan_label': jenis_laporan_labels.get(jenis_laporan, 'Laporan'),
        'produk_id': produk_id,
        'chanel_id': chanel_id,
        'kategori_filter': kategori_filter,
        'lokasi_filter': lokasi_filter,
        'selected_produk': selected_produk,
        'selected_chanel': selected_chanel,
        'start_date': start_date.strftime('%Y-%m-%d') if start_date else '',
        'end_date': end_date.strftime('%Y-%m-%d') if end_date else '',
        'periode_label': periode_label,
        'periode_preset': request.GET.get('periode_preset', ''),
        'laporan_data': laporan_data,
        'ringkasan': ringkasan,
        'show_report': show_report == '1' or bool(request.GET.get('jenis_laporan')),
        'grafik_data': _json.dumps(grafik_data),
        'generated_at': datetime.now(),
    }

    return render(request, 'inventory/laporan.html', context)


# ==================================================
# EKSPOR LAPORAN (EXCEL & CSV) — MENGIKUTI FILTER AKTIF
# ==================================================

@login_required
def ekspor_laporan_excel(request):
    """Ekspor laporan ke file Excel (.xlsx) mengikuti filter aktif."""
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    jenis_laporan = request.GET.get('jenis_laporan', 'stok_saat_ini').strip()
    produk_id = request.GET.get('produk_id', '').strip()
    kategori_filter = request.GET.get('kategori', '').strip()
    chanel_id = request.GET.get('chanel_id', '').strip()

    start_date, end_date, periode_label = _get_date_range(request)

    selected_produk = None
    if produk_id:
        try:
            selected_produk = Produk.objects.get(id=produk_id)
        except (Produk.DoesNotExist, ValueError):
            produk_id = ''

    jenis_labels = {
        'stok_saat_ini': 'Laporan Stok Saat Ini',
        'barang_masuk': 'Laporan Barang Masuk',
        'barang_keluar': 'Laporan Barang Keluar',
        'distribusi': 'Laporan Distribusi',
        'pergerakan_stok': 'Laporan Pergerakan Stok',
        'stok_menipis': 'Laporan Stok Menipis',
        'rekapitulasi': 'Laporan Rekapitulasi per Produk',
    }
    nama_laporan = jenis_labels.get(jenis_laporan, 'Laporan Inventori')

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Laporan'

    header_fill = PatternFill(start_color='0B2D5C', end_color='0B2D5C', fill_type='solid')
    title_font = Font(bold=True, size=14, color='0B2D5C')
    sub_font = Font(size=10, color='555555')
    center_align = Alignment(horizontal='center', vertical='center')
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin'),
    )
    low_fill = PatternFill(start_color='FFEAEA', end_color='FFEAEA', fill_type='solid')

    ws.merge_cells('A1:G1')
    ws['A1'] = 'RUMAH BUMN PURBALINGGA'
    ws['A1'].font = Font(bold=True, size=16, color='0B2D5C')
    ws['A1'].alignment = center_align

    ws.merge_cells('A2:G2')
    ws['A2'] = nama_laporan
    ws['A2'].font = title_font
    ws['A2'].alignment = center_align

    ws.merge_cells('A3:G3')
    ws['A3'] = f'Periode: {periode_label}'
    ws['A3'].font = sub_font
    ws['A3'].alignment = center_align

    filter_produk_label = selected_produk.nama_produk if selected_produk else 'Semua Produk'
    ws.merge_cells('A4:G4')
    ws['A4'] = f'Produk: {filter_produk_label}  |  Dicetak: {datetime.now().strftime("%d/%m/%Y %H:%M")}'
    ws['A4'].font = sub_font
    ws['A4'].alignment = center_align

    ws.row_dimensions[1].height = 22
    ws.row_dimensions[2].height = 18
    ws.row_dimensions[3].height = 14
    ws.row_dimensions[4].height = 14

    ws.append([])
    row_start = 6

    def style_header_row(ws, row, num_cols):
        for col in range(1, num_cols + 1):
            cell = ws.cell(row=row, column=col)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = center_align
            cell.border = thin_border

    def style_data_row(ws, row, num_cols, alt=False, low=False):
        alt_fill = PatternFill(start_color='F5F9FF', end_color='F5F9FF', fill_type='solid')
        for col in range(1, num_cols + 1):
            cell = ws.cell(row=row, column=col)
            cell.border = thin_border
            if low:
                cell.fill = low_fill
            elif alt:
                cell.fill = alt_fill

    if jenis_laporan == 'stok_saat_ini':
        headers = ['No', 'Kode Produk', 'Nama Produk', 'Kategori', 'UMKM/Pemilik', 'Stok Kantor', 'Stok Bazar', 'Total Stok', 'Stok Minimum', 'Status']
        ws.append(headers)
        style_header_row(ws, row_start, len(headers))

        qs = Stok.objects.select_related('produk', 'produk__umkm').all()
        if produk_id:
            qs = qs.filter(produk_id=produk_id)
        if kategori_filter:
            qs = qs.filter(produk__kategori__iexact=kategori_filter)

        for idx, s in enumerate(qs, 1):
            sc = s.stok_chanel
            tot = s.stok_kantor + sc
            status = s.produk.status_stok
            row = [idx, s.produk.kode_produk, s.produk.nama_produk, s.produk.kategori or '-',
                   s.produk.umkm.nama if s.produk.umkm else '-',
                   s.stok_kantor, sc, tot, s.produk.stok_minimum, status.capitalize()]
            ws.append(row)
            is_low = status in ['menipis', 'habis']
            style_data_row(ws, row_start + idx, len(headers), alt=(idx % 2 == 0), low=is_low)

    elif jenis_laporan == 'barang_masuk':
        headers = ['No', 'Tanggal', 'Kode Produk', 'Nama Produk', 'Jumlah Masuk', 'Asal', 'Keterangan']
        ws.append(headers)
        style_header_row(ws, row_start, len(headers))
        qs = BarangMasuk.objects.select_related('produk').order_by('-tanggal')
        if produk_id:
            qs = qs.filter(produk_id=produk_id)
        if kategori_filter:
            qs = qs.filter(produk__kategori__iexact=kategori_filter)
        qs = _apply_date_filter(qs, start_date, end_date)
        for idx, bm in enumerate(qs, 1):
            ws.append([idx, bm.tanggal.strftime('%d/%m/%Y %H:%M'), bm.produk.kode_produk,
                       bm.produk.nama_produk, bm.jumlah, bm.asal or '-', bm.keterangan or '-'])
            style_data_row(ws, row_start + idx, len(headers), alt=(idx % 2 == 0))

    elif jenis_laporan == 'barang_keluar':
        headers = ['No', 'Tanggal', 'Kode Produk', 'Nama Produk', 'Jumlah Keluar', 'Tujuan', 'Keterangan']
        ws.append(headers)
        style_header_row(ws, row_start, len(headers))
        qs = BarangKeluar.objects.select_related('produk').order_by('-tanggal')
        if produk_id:
            qs = qs.filter(produk_id=produk_id)
        if kategori_filter:
            qs = qs.filter(produk__kategori__iexact=kategori_filter)
        qs = _apply_date_filter(qs, start_date, end_date)
        for idx, bk in enumerate(qs, 1):
            ws.append([idx, bk.tanggal.strftime('%d/%m/%Y %H:%M'), bk.produk.kode_produk,
                       bk.produk.nama_produk, bk.jumlah, bk.tujuan or '-', bk.keterangan or '-'])
            style_data_row(ws, row_start + idx, len(headers), alt=(idx % 2 == 0))

    elif jenis_laporan == 'distribusi':
        headers = ['No', 'Tanggal', 'Kode Produk', 'Nama Produk', 'Asal', 'Tujuan/Chanel', 'Jumlah', 'Keterangan']
        ws.append(headers)
        style_header_row(ws, row_start, len(headers))
        qs = Distribusi.objects.select_related('produk', 'chanel').order_by('-tanggal')
        if produk_id:
            qs = qs.filter(produk_id=produk_id)
        if kategori_filter:
            qs = qs.filter(produk__kategori__iexact=kategori_filter)
        if chanel_id:
            qs = qs.filter(chanel_id=chanel_id)
        qs = _apply_date_filter(qs, start_date, end_date)
        for idx, d in enumerate(qs, 1):
            tujuan_str = d.chanel.nama_toko if d.chanel else (d.tujuan or '-')
            ws.append([idx, d.tanggal.strftime('%d/%m/%Y %H:%M'), d.produk.kode_produk,
                       d.produk.nama_produk, d.asal or '-', tujuan_str, d.jumlah, d.keterangan or '-'])
            style_data_row(ws, row_start + idx, len(headers), alt=(idx % 2 == 0))

    elif jenis_laporan == 'pergerakan_stok':
        headers = ['No', 'Kode Produk', 'Nama Produk', 'Kategori', 'Stok Awal', 'Total Masuk', 'Total Keluar', 'Total Distribusi', 'Penyesuaian', 'Stok Akhir']
        ws.append(headers)
        style_header_row(ws, row_start, len(headers))
        produk_qs = Produk.objects.select_related('umkm').all()
        if produk_id:
            produk_qs = produk_qs.filter(id=produk_id)
        if kategori_filter:
            produk_qs = produk_qs.filter(kategori__iexact=kategori_filter)
        idx = 0
        for p in produk_qs:
            try:
                stok_obj = p.stok
                stok_akhir = stok_obj.stok_kantor
            except Stok.DoesNotExist:
                stok_akhir = 0
            masuk_qs = _apply_date_filter(BarangMasuk.objects.filter(produk=p), start_date, end_date)
            keluar_qs = _apply_date_filter(BarangKeluar.objects.filter(produk=p), start_date, end_date)
            dist_qs = _apply_date_filter(Distribusi.objects.filter(produk=p), start_date, end_date)
            peny_qs = _apply_date_filter(RiwayatStok.objects.filter(produk=p, jenis_transaksi='PENYESUAIAN'), start_date, end_date)
            total_masuk = masuk_qs.aggregate(t=Sum('jumlah'))['t'] or 0
            total_keluar = keluar_qs.aggregate(t=Sum('jumlah'))['t'] or 0
            total_dist = dist_qs.aggregate(t=Sum('jumlah'))['t'] or 0
            total_peny = peny_qs.aggregate(t=Sum('jumlah'))['t'] or 0
            if total_masuk > 0 or total_keluar > 0 or total_dist > 0 or total_peny != 0 or produk_id:
                idx += 1
                stok_awal = max(stok_akhir - total_masuk + total_keluar + total_dist - total_peny, 0)
                ws.append([idx, p.kode_produk, p.nama_produk, p.kategori or '-',
                           stok_awal, total_masuk, total_keluar, total_dist, total_peny, stok_akhir])
                style_data_row(ws, row_start + idx, len(headers), alt=(idx % 2 == 0))

    elif jenis_laporan == 'stok_menipis':
        headers = ['No', 'Kode Produk', 'Nama Produk', 'Kategori', 'UMKM/Pemilik', 'Stok Kantor', 'Stok Bazar', 'Total Stok', 'Stok Minimum', 'Kekurangan', 'Status']
        ws.append(headers)
        style_header_row(ws, row_start, len(headers))
        qs = Stok.objects.select_related('produk', 'produk__umkm').all()
        if produk_id:
            qs = qs.filter(produk_id=produk_id)
        if kategori_filter:
            qs = qs.filter(produk__kategori__iexact=kategori_filter)
        idx = 0
        for s in qs:
            sc = s.stok_chanel
            tot = s.stok_kantor + sc
            min_stok = s.produk.stok_minimum
            if tot <= min_stok:
                idx += 1
                ws.append([idx, s.produk.kode_produk, s.produk.nama_produk, s.produk.kategori or '-',
                           s.produk.umkm.nama if s.produk.umkm else '-',
                           s.stok_kantor, sc, tot, min_stok, max(min_stok - tot, 0),
                           'Habis' if tot <= 0 else 'Menipis'])
                style_data_row(ws, row_start + idx, len(headers), low=True)

    elif jenis_laporan == 'rekapitulasi':
        headers = ['No', 'Kode Produk', 'Nama Produk', 'Kategori', 'UMKM/Pemilik', 'Jml Transaksi', 'Total Masuk', 'Total Keluar', 'Total Distribusi', 'Stok Kantor', 'Stok Bazar', 'Total Stok']
        ws.append(headers)
        style_header_row(ws, row_start, len(headers))
        produk_qs = Produk.objects.select_related('umkm').all()
        if produk_id:
            produk_qs = produk_qs.filter(id=produk_id)
        if kategori_filter:
            produk_qs = produk_qs.filter(kategori__iexact=kategori_filter)
        idx = 0
        for p in produk_qs:
            masuk_qs = _apply_date_filter(BarangMasuk.objects.filter(produk=p), start_date, end_date)
            keluar_qs = _apply_date_filter(BarangKeluar.objects.filter(produk=p), start_date, end_date)
            dist_qs = _apply_date_filter(Distribusi.objects.filter(produk=p), start_date, end_date)

            total_masuk = masuk_qs.aggregate(t=Sum('jumlah'))['t'] or 0
            total_keluar = keluar_qs.aggregate(t=Sum('jumlah'))['t'] or 0
            total_dist = dist_qs.aggregate(t=Sum('jumlah'))['t'] or 0
            jml_transaksi = masuk_qs.count() + keluar_qs.count() + dist_qs.count()

            try:
                stok_obj = p.stok
                stok_k = stok_obj.stok_kantor
                stok_b = stok_obj.stok_chanel
            except Stok.DoesNotExist:
                stok_k = 0
                stok_b = 0

            if jml_transaksi > 0 or produk_id:
                idx += 1
                ws.append([idx, p.kode_produk, p.nama_produk, p.kategori or '-',
                           p.umkm.nama if p.umkm else '-',
                           jml_transaksi, total_masuk, total_keluar, total_dist, stok_k, stok_b, stok_k + stok_b])
                style_data_row(ws, row_start + idx, len(headers), alt=(idx % 2 == 0))

    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            try:
                if cell.value:
                    max_len = max(max_len, len(str(cell.value)))
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = min(max_len + 4, 40)

    filename = f"laporan_{jenis_laporan}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response


@login_required
def ekspor_laporan_csv(request):
    """Ekspor laporan ke CSV mengikuti filter aktif."""
    jenis_laporan = request.GET.get('jenis_laporan', 'stok_saat_ini').strip()
    produk_id = request.GET.get('produk_id', '').strip()
    kategori_filter = request.GET.get('kategori', '').strip()
    chanel_id = request.GET.get('chanel_id', '').strip()

    start_date, end_date, periode_label = _get_date_range(request)

    filename = f"laporan_{jenis_laporan}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response.write('﻿')  # BOM UTF-8 for Excel
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(['RUMAH BUMN PURBALINGGA'])
    writer.writerow([f'Laporan: {jenis_laporan.replace("_", " ").title()}'])
    writer.writerow([f'Periode: {periode_label}'])
    writer.writerow([f'Dicetak: {datetime.now().strftime("%d/%m/%Y %H:%M")}'])
    writer.writerow([])

    if jenis_laporan == 'stok_saat_ini':
        writer.writerow(['No', 'Kode Produk', 'Nama Produk', 'Kategori', 'UMKM/Pemilik', 'Stok Kantor', 'Stok Bazar', 'Total Stok', 'Stok Minimum', 'Status'])
        qs = Stok.objects.select_related('produk', 'produk__umkm').all()
        if produk_id:
            qs = qs.filter(produk_id=produk_id)
        if kategori_filter:
            qs = qs.filter(produk__kategori__iexact=kategori_filter)
        for idx, s in enumerate(qs, 1):
            sc = s.stok_chanel
            tot = s.stok_kantor + sc
            writer.writerow([idx, s.produk.kode_produk, s.produk.nama_produk, s.produk.kategori or '-',
                             s.produk.umkm.nama if s.produk.umkm else '-',
                             s.stok_kantor, sc, tot, s.produk.stok_minimum, s.produk.status_stok])

    elif jenis_laporan == 'barang_masuk':
        writer.writerow(['No', 'Tanggal', 'Kode Produk', 'Nama Produk', 'Jumlah', 'Asal', 'Keterangan'])
        qs = BarangMasuk.objects.select_related('produk').order_by('-tanggal')
        if produk_id:
            qs = qs.filter(produk_id=produk_id)
        if kategori_filter:
            qs = qs.filter(produk__kategori__iexact=kategori_filter)
        qs = _apply_date_filter(qs, start_date, end_date)
        for idx, bm in enumerate(qs, 1):
            writer.writerow([idx, bm.tanggal.strftime('%d/%m/%Y %H:%M'), bm.produk.kode_produk,
                             bm.produk.nama_produk, bm.jumlah, bm.asal or '-', bm.keterangan or '-'])

    elif jenis_laporan == 'barang_keluar':
        writer.writerow(['No', 'Tanggal', 'Kode Produk', 'Nama Produk', 'Jumlah', 'Tujuan', 'Keterangan'])
        qs = BarangKeluar.objects.select_related('produk').order_by('-tanggal')
        if produk_id:
            qs = qs.filter(produk_id=produk_id)
        if kategori_filter:
            qs = qs.filter(produk__kategori__iexact=kategori_filter)
        qs = _apply_date_filter(qs, start_date, end_date)
        for idx, bk in enumerate(qs, 1):
            writer.writerow([idx, bk.tanggal.strftime('%d/%m/%Y %H:%M'), bk.produk.kode_produk,
                             bk.produk.nama_produk, bk.jumlah, bk.tujuan or '-', bk.keterangan or '-'])

    elif jenis_laporan == 'distribusi':
        writer.writerow(['No', 'Tanggal', 'Kode Produk', 'Nama Produk', 'Asal', 'Tujuan/Chanel', 'Jumlah', 'Keterangan'])
        qs = Distribusi.objects.select_related('produk', 'chanel').order_by('-tanggal')
        if produk_id:
            qs = qs.filter(produk_id=produk_id)
        if chanel_id:
            qs = qs.filter(chanel_id=chanel_id)
        qs = _apply_date_filter(qs, start_date, end_date)
        for idx, d in enumerate(qs, 1):
            tujuan_str = d.chanel.nama_toko if d.chanel else (d.tujuan or 'Chanel')
            writer.writerow([idx, d.tanggal.strftime('%d/%m/%Y %H:%M'), d.produk.kode_produk,
                             d.produk.nama_produk, d.jumlah, d.asal, tujuan_str, d.keterangan or '-'])

    elif jenis_laporan == 'stok_menipis':
        writer.writerow(['No', 'Kode Produk', 'Nama Produk', 'Kategori', 'UMKM', 'Stok Saat Ini', 'Stok Minimum', 'Kekurangan', 'Status'])
        qs = Stok.objects.select_related('produk', 'produk__umkm').all()
        if produk_id:
            qs = qs.filter(produk_id=produk_id)
        if kategori_filter:
            qs = qs.filter(produk__kategori__iexact=kategori_filter)
        idx = 0
        for s in qs:
            sc = s.stok_chanel
            tot = s.stok_kantor + sc
            if tot <= s.produk.stok_minimum:
                idx += 1
                writer.writerow([idx, s.produk.kode_produk, s.produk.nama_produk, s.produk.kategori or '-',
                                 s.produk.umkm.nama if s.produk.umkm else '-',
                                 tot, s.produk.stok_minimum, max(s.produk.stok_minimum - tot, 0),
                                 'Habis' if tot <= 0 else 'Menipis'])

    else:
        writer.writerow(['Jenis laporan tidak dikenali untuk ekspor CSV.'])

    return response


# ==================================================
# EKSPOR DATA MASTER (CSV)
# ==================================================

@login_required
def ekspor_csv(request, data_type):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response.write('\ufeff')

    writer = csv.writer(response)

    if data_type == 'produk':
        response['Content-Disposition'] = 'attachment; filename="data_produk.csv"'
        writer.writerow(['No', 'Kode Produk', 'Nama Produk', 'Pemilik', 'UMKM', 'Kategori', 'Harga Beli (Rp)', 'Harga Jual (Rp)', 'Stok Minimum'])
        for idx, item in enumerate(Produk.objects.select_related('umkm').all(), 1):
            writer.writerow([
                idx,
                item.kode_produk,
                item.nama_produk,
                item.nama_pemilik or '-',
                item.umkm.nama if item.umkm else '-',
                item.kategori or '-',
                f"{item.harga_beli:.2f}",
                f"{item.harga_jual:.2f}",
                item.stok_minimum
            ])

    elif data_type == 'umkm':
        response['Content-Disposition'] = 'attachment; filename="data_umkm.csv"'
        writer.writerow(['No', 'Nama UMKM', 'Pemilik', 'Jenis Usaha', 'Tanggal Terdaftar', 'Kontak / Telp', 'Alamat', 'Total Produk'])
        for idx, item in enumerate(UMKM.objects.all(), 1):
            tgl = item.tanggal_terdaftar.strftime('%d-%m-%Y') if item.tanggal_terdaftar else '-'
            writer.writerow([
                idx,
                item.nama,
                item.pemilik or '-',
                item.jenis_usaha,
                tgl,
                item.kontak or '-',
                item.alamat or '-',
                item.total_produk
            ])

    elif data_type == 'kantor':
        response['Content-Disposition'] = 'attachment; filename="data_stok_kantor.csv"'
        writer.writerow(['No', 'Kode Produk', 'Nama Produk', 'Kategori', 'UMKM', 'Stok Kantor', 'Batas Minimum', 'Status'])
        for idx, item in enumerate(Stok.objects.select_related('produk', 'produk__umkm').all(), 1):
            writer.writerow([
                idx,
                item.produk.kode_produk,
                item.produk.nama_produk,
                item.produk.kategori or '-',
                item.produk.umkm.nama if item.produk.umkm else '-',
                item.stok_kantor,
                item.produk.stok_minimum,
                item.status
            ])

    elif data_type == 'stok':
        response['Content-Disposition'] = 'attachment; filename="data_rekap_stok.csv"'
        writer.writerow(['No', 'Kode Produk', 'Nama Produk', 'Kategori', 'UMKM', 'Stok Kantor', 'Stok Chanel', 'Total Stok', 'Status'])
        for idx, item in enumerate(Stok.objects.select_related('produk', 'produk__umkm').all(), 1):
            writer.writerow([
                idx,
                item.produk.kode_produk,
                item.produk.nama_produk,
                item.produk.kategori or '-',
                item.produk.umkm.nama if item.produk.umkm else '-',
                item.stok_kantor,
                item.stok_chanel,
                item.total_stok,
                item.status
            ])

    elif data_type == 'barang_masuk':
        response['Content-Disposition'] = 'attachment; filename="data_barang_masuk.csv"'
        writer.writerow(['No', 'Tanggal', 'Kode Produk', 'Nama Produk', 'Jumlah', 'Asal', 'Tujuan', 'Keterangan'])
        for idx, item in enumerate(BarangMasuk.objects.select_related('produk').all(), 1):
            writer.writerow([
                idx,
                item.tanggal.strftime('%d-%m-%Y %H:%M'),
                item.produk.kode_produk,
                item.produk.nama_produk,
                item.jumlah,
                item.asal or '-',
                item.tujuan,
                item.keterangan or '-'
            ])

    elif data_type == 'barang_keluar':
        response['Content-Disposition'] = 'attachment; filename="data_barang_keluar.csv"'
        writer.writerow(['No', 'Tanggal', 'Kode Produk', 'Nama Produk', 'Jumlah', 'Asal', 'Tujuan', 'Keterangan'])
        for idx, item in enumerate(BarangKeluar.objects.select_related('produk').all(), 1):
            writer.writerow([
                idx,
                item.tanggal.strftime('%d-%m-%Y %H:%M'),
                item.produk.kode_produk,
                item.produk.nama_produk,
                item.jumlah,
                item.asal,
                item.tujuan or '-',
                item.keterangan or '-'
            ])

    elif data_type == 'distribusi':
        response['Content-Disposition'] = 'attachment; filename="data_distribusi.csv"'
        writer.writerow(['No', 'Tanggal', 'Kode Produk', 'Nama Produk', 'Jumlah', 'Asal', 'Tujuan (Chanel)', 'Keterangan'])
        for idx, item in enumerate(Distribusi.objects.select_related('produk', 'chanel').all(), 1):
            tujuan_str = item.chanel.nama_toko if item.chanel else (item.tujuan or 'Chanel')
            writer.writerow([
                idx,
                item.tanggal.strftime('%d/%m/%Y %H:%M'),
                item.produk.kode_produk,
                item.produk.nama_produk,
                item.jumlah,
                item.asal,
                tujuan_str,
                item.keterangan or '-'
            ])

    else:
        return HttpResponse("Tipe data ekspor tidak dikenali.", status=400)

    return response


# ==================================================
# AUTHENTICATION
# ==================================================

def user_logout(request):
    logout(request)
    messages.success(request, 'Anda telah berhasil logout.')
    return redirect('login')


# ==================================================
# FITUR HAPUS SEMUA DATA (BULK DELETE SECURE)
# ==================================================

@login_required
def hapus_semua_data(request, data_type):
    """
    View untuk menghapus semua data berdasarkan jenis data pada halaman yang sedang dibuka.
    Dilindungi dengan validasi HTTP POST, CSRF, login, dan frasa konfirmasi 'HAPUS SEMUA DATA'.
    """
    redirect_map = {
        'umkm': 'data_umkm',
        'produk': 'data_produk',
        'kantor': 'data_kantor',
        'stok': 'data_stok',
        'chanel': 'data_bazar',
        'distribusi': 'data_distribusi',
        'barang_masuk': 'data_barang_masuk',
        'barang_keluar': 'data_barang_keluar',
    }

    redirect_url = redirect_map.get(data_type, 'dashboard')

    if request.method != 'POST':
        messages.error(request, "Aksi tidak diizinkan. Penghapusan seluruh data harus menggunakan metode HTTP POST.")
        return redirect(redirect_url)

    frasa = request.POST.get('konfirmasi_frasa', '').strip()
    if frasa != 'HAPUS SEMUA DATA':
        messages.error(
            request,
            "Penghapusan dibatalkan! Frasa konfirmasi tidak sesuai. Harap ketik 'HAPUS SEMUA DATA' dengan tepat."
        )
        return redirect(redirect_url)

    try:
        with transaction.atomic():
            if data_type == 'umkm':
                count = UMKM.objects.count()
                if count == 0:
                    messages.info(request, "Tidak ada data UMKM yang dapat dihapus.")
                    return redirect('data_umkm')
                UMKM.objects.all().delete()
                messages.success(request, f"Seluruh data UMKM ({count} mitra UMKM) berhasil dihapus.")
                return redirect('data_umkm')

            elif data_type == 'produk':
                count = Produk.objects.count()
                if count == 0:
                    messages.info(request, "Tidak ada data produk yang dapat dihapus.")
                    return redirect('data_produk')
                Produk.objects.all().delete()
                messages.success(request, f"Seluruh data produk ({count} produk) berhasil dihapus.")
                return redirect('data_produk')

            elif data_type in ['kantor', 'stok']:
                target = 'data_kantor' if data_type == 'kantor' else 'data_stok'
                stok_qs = Stok.objects.select_for_update().filter(stok_kantor__gt=0)
                count = stok_qs.count()
                total_unit = Stok.objects.aggregate(t=Sum('stok_kantor'))['t'] or 0

                if count == 0 and total_unit == 0:
                    messages.info(request, "Stok kantor sudah dalam keadaan kosong (0 unit).")
                    return redirect(target)

                for s in stok_qs:
                    stok_lama = s.stok_kantor
                    s.stok_kantor = 0
                    s.save()
                    RiwayatStok.objects.create(
                        produk=s.produk,
                        jenis_transaksi='PENYESUAIAN',
                        jumlah=-stok_lama,
                        stok_sebelum=stok_lama,
                        stok_sesudah=0,
                        lokasi='Kantor',
                        keterangan="Reset seluruh stok kantor menjadi 0 unit"
                    )

                messages.success(
                    request,
                    f"Seluruh stok kantor ({count} produk, total {total_unit} unit) berhasil dikosongkan."
                )
                return redirect(target)

            elif data_type == 'chanel':
                count = Chanel.objects.count()
                if count == 0:
                    messages.info(request, "Tidak ada data Channel/Toko yang dapat dihapus.")
                    return redirect('data_bazar')
                Chanel.objects.all().delete()
                messages.success(request, f"Seluruh data Channel/Toko ({count} toko) berhasil dihapus.")
                return redirect('data_bazar')

            elif data_type == 'distribusi':
                count = Distribusi.objects.count()
                if count == 0:
                    messages.info(request, "Tidak ada data riwayat distribusi yang dapat dihapus.")
                    return redirect('data_distribusi')
                Distribusi.objects.all().delete()
                RiwayatStok.objects.filter(jenis_transaksi__in=['DISTRIBUSI', 'KEMBALI_DISTRIBUSI']).delete()
                messages.success(
                    request,
                    f"Seluruh riwayat Distribusi ({count} transaksi) berhasil dihapus. Saldo stok kantor dan toko tetap konsisten."
                )
                return redirect('data_distribusi')

            elif data_type == 'barang_masuk':
                count = BarangMasuk.objects.count()
                if count == 0:
                    messages.info(request, "Tidak ada data barang masuk yang dapat dihapus.")
                    return redirect('data_barang_masuk')
                BarangMasuk.objects.all().delete()
                RiwayatStok.objects.filter(jenis_transaksi='MASUK').delete()
                messages.success(
                    request,
                    f"Seluruh riwayat Barang Masuk ({count} transaksi) berhasil dihapus."
                )
                return redirect('data_barang_masuk')

            elif data_type == 'barang_keluar':
                count = BarangKeluar.objects.count()
                if count == 0:
                    messages.info(request, "Tidak ada data barang keluar yang dapat dihapus.")
                    return redirect('data_barang_keluar')
                BarangKeluar.objects.all().delete()
                RiwayatStok.objects.filter(jenis_transaksi='KELUAR').delete()
                messages.success(
                    request,
                    f"Seluruh riwayat Barang Keluar ({count} transaksi) berhasil dihapus."
                )
                return redirect('data_barang_keluar')

            else:
                messages.error(request, f"Tipe data '{data_type}' tidak valid.")
                return redirect('dashboard')

    except Exception as e:
        messages.error(request, f"Terjadi kesalahan!: {str(e)}")
        return redirect(redirect_url)