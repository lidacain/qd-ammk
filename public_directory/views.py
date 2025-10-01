from django.shortcuts import render
from django.db.models import Q
from django.db.models.functions import Lower
from users.models import HelpdeskContact  # 👈 Импортируй существующую модель
import re
from django.db import DatabaseError
from django.db.models import Q, F, Value, CharField
from django.db.models.functions import Lower
from django.db.models import Func


# Удаляет все нецифры
def normalize_digits(s: str) -> str:
    return re.sub(r"\D+", "", s or "")


# Аналог PostgreSQL REGEXP_REPLACE(text, pattern, replacement, flags)
class RegexReplace(Func):
    function = "REGEXP_REPLACE"
    arity = 4  # text, pattern, replacement, flags
    output_field = CharField()



def public_helpdesk_directory(request):
    query = request.GET.get("q", "").strip()
    contacts = HelpdeskContact.objects.all().order_by(Lower("department"))

    if query:
        q_objects = Q()
        # Текстовые поля
        for variant in (query, query.lower(), query.title(), query.upper()):
            q_objects |= Q(employee_name__icontains=variant)
            q_objects |= Q(department__icontains=variant)
            q_objects |= Q(position__icontains=variant)
            q_objects |= Q(email__icontains=variant)

        # Телефон: сравниваем только цифры
        q_digits = normalize_digits(query)
        if q_digits:
            try:
                # PostgreSQL путь — быстро и по БД
                contacts = contacts.annotate(
                    phone_digits=RegexReplace(F("phone_number"), Value(r"\D+"), Value(""), Value("g"))
                )
                q_objects |= Q(phone_digits__icontains=q_digits)
                contacts = contacts.filter(q_objects)
            except DatabaseError:
                # Фоллбэк (SQLite/другая БД): фильтруем по Python
                ids = [c.id for c in contacts if q_digits in normalize_digits(c.phone_number)]
                contacts = contacts.filter(q_objects | Q(id__in=ids))
        else:
            contacts = contacts.filter(q_objects)

    return render(request, "public_directory/directory.html", {
        "contacts": contacts,
        "query": query,
        "enable_particles": True,
        "enable_background": True,
        "enable_white_square": False
    })

