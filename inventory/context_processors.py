from django.db.models import F, Value
from django.db.models.functions import Coalesce
from .models import Stok

def notifikasi_stok(request):
    """
    Context processor untuk menyediakan jumlah stok menipis
    secara global ke header aplikasi di semua halaman.
    """
    if request.user.is_authenticated:
        try:
            count = (
                Stok.objects.annotate(
                    total_stok=F('stok_kantor') + Coalesce(Value(0), Value(0))
                )
                .filter(stok_kantor__lte=F('produk__stok_minimum'))
                .count()
            )
            return {'notifikasi_stok_count': count}
        except Exception:
            return {'notifikasi_stok_count': 0}
    return {'notifikasi_stok_count': 0}
