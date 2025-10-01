from django.db import models
from django.utils.timezone import now
from django.conf import settings
from django.utils.text import slugify
from copy import deepcopy
from django.utils import timezone



class VINHistory(models.Model):
    vin = models.CharField(max_length=17, unique=True, verbose_name="VIN номер автомобиля")
    history = models.JSONField(default=dict, verbose_name="История контроля")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата добавления")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Последнее обновление")

    def add_entry(self, post, defects=None, extra_data=None):
        if defects is None:
            defects = []
        if extra_data is None:
            extra_data = {}

        zone = post.location
        post_name = post.name

        self.history.setdefault(zone, {})
        self.history[zone].setdefault(post_name, [])

        entries = self.history[zone][post_name]

        # Найдём следующий индекс записи:
        max_entry_idx = 0
        for e in entries:
            try:
                max_entry_idx = max(max_entry_idx, int(e.get("entry_index", 0)))
            except Exception:
                pass
        next_entry_idx = max_entry_idx + 1

        zone_slug = slugify(zone, allow_unicode=True)
        post_slug = slugify(post_name, allow_unicode=True)

        # Сформируем запись
        inspection_data = {
            "defects": defects,
            "extra_data": extra_data,
            "date_added": now().isoformat(),
            "entry_index": next_entry_idx,
            "id": f"{self.vin}-{zone_slug}-{post_slug}-{next_entry_idx}",
        }

        # Проставим id дефектам
        max_defect_idx = 0
        for idx, d in enumerate(inspection_data["defects"], start=1):
            # если уже есть индексы — уважаем их и считаем максимум
            try:
                max_defect_idx = max(max_defect_idx, int(d.get("defect_index", 0)))
            except Exception:
                pass
        cur = max_defect_idx
        for d in inspection_data["defects"]:
            if "defect_index" not in d:
                cur += 1
                d["defect_index"] = cur
            d["id"] = f"{self.vin}-{zone_slug}-{post_slug}-{next_entry_idx}-{d['defect_index']}"

        entries.append(inspection_data)
        self.save(update_fields=["history", "updated_at"])
        return inspection_data["id"]  # можно вернуть ID записи для удобства

    # Удобные методы редактирования по ID:
    def update_entry(self, entry_id: str, **fields) -> bool:
        """
        Обновить поля записи (например: controller, line, has_defect, extra_data и пр.)
        Перед обновлением сохраняется бэкап предыдущего состояния записи.
        Возвращает True, если успешно.
        """
        h = self.history or {}
        for zone, posts in h.items():
            for post, entries in (posts or {}).items():
                for e in entries:
                    if e.get("id") == entry_id:
                        # backup предыдущего состояния
                        try:
                            VINHistoryBackup.objects.create(
                                vin=self.vin,
                                post=post,
                                zone=zone,
                                entry=deepcopy(e),
                                action="edit",
                            )
                        except Exception:
                            # лог пропускаем, чтобы не ронять транзакцию
                            pass

                        # обновляем только простые поля (defects редактируются отдельно)
                        for k, v in fields.items():
                            if k == "defects":
                                continue
                            e[k] = v

                        self.save(update_fields=["history", "updated_at"])
                        return True
        return False

    def update_defect(self, defect_id: str, **fields) -> bool:
        """
        Обновить поля конкретного дефекта по его ID (name, unit, grade, photos, comment, ...).
        Перед обновлением сохраняется бэкап предыдущего состояния дефекта.
        Возвращает True, если успешно.
        """
        h = self.history or {}
        for zone, posts in h.items():
            for post, entries in (posts or {}).items():
                for e in entries:
                    for d in e.get("defects", []):
                        if d.get("id") == defect_id:
                            try:
                                VINHistoryBackup.objects.create(
                                    vin=self.vin,
                                    post=post,
                                    zone=zone,
                                    entry={"type": "defect", "entry_id": e.get("id"), "data": deepcopy(d)},
                                    action="edit",
                                )
                            except Exception:
                                pass

                            for k, v in fields.items():
                                d[k] = v

                            self.save(update_fields=["history", "updated_at"])
                            return True
        return False

    def get_entry_by_id(self, entry_id: str):
        """Возвращает (zone, post, entry_dict, entries_list) или (None, None, None, None), если не найдено."""
        h = self.history or {}
        for zone, posts in h.items():
            for post, entries in (posts or {}).items():
                for e in entries:
                    if e.get("id") == entry_id:
                        return zone, post, e, entries
        return None, None, None, None

    def update_entry_extra(self, entry_id: str, **extra_fields) -> bool:
        """
        Добавляет/обновляет дополнительные поля внутри entry.extra_data.
        Пример: update_entry_extra(entry_id, qrr_responsible="Иванов", qrr_comment="Согласовано")
        Возвращает True, если успешно.
        """
        zone, post, entry, _ = self.get_entry_by_id(entry_id)
        if entry is None:
            return False

        # backup полного entry перед изменением
        try:
            VINHistoryBackup.objects.create(
                vin=self.vin,
                post=post,
                zone=zone,
                entry=deepcopy(entry),
                action="edit",
            )
        except Exception:
            pass
# MXMDB21B1SK000050-цех-сборки-интерьер-1
        extra = entry.get("extra_data") or {}
        if not isinstance(extra, dict):
            extra = {}

        # мержим поля
        for k, v in extra_fields.items():
            extra[k] = v

        entry["extra_data"] = extra
        self.save(update_fields=["history", "updated_at"])
        return True

    def set_qrr_responsible(self, entry_id: str, responsible: str, **kwargs) -> bool:
        """
        Удобный шорткат для записи ответственного от QRR в extra_data.
        Можно передать дополнительные поля, например qrr_comment="...", qrr_ticket="...".
        """
        fields = {"qrr_responsible": responsible}
        fields.update(kwargs)
        return self.update_entry_extra(entry_id, **fields)

    def get_defect_by_id(self, defect_id: str):
        """Возвращает (zone, post, entry_dict, defect_dict, defects_list) или (None, None, None, None, None)."""
        h = self.history or {}
        for zone, posts in h.items():
            for post, entries in (posts or {}).items():
                for e in entries:
                    defs = e.get("defects", [])
                    for d in defs:
                        if d.get("id") == defect_id:
                            return zone, post, e, d, defs
        return None, None, None, None, None

    def update_defect_extra(self, defect_id: str, **extra_fields) -> bool:
        """
        Добавляет/обновляет дополнительные поля у дефекта в словаре defect['extra'].
        Это безопасно: не перетирает базовые поля дефекта (name, unit, grade, photos, ...).
        Пример: update_defect_extra(defect_id, qrr_responsible="Иванов", qrr_comment="...", root_cause="...")
        Возвращает True, если успешно.
        """
        zone, post, entry, defect, _ = self.get_defect_by_id(defect_id)
        if defect is None:
            return False

        # backup исходного дефекта
        try:
            VINHistoryBackup.objects.create(
                vin=self.vin,
                post=post,
                zone=zone,
                entry={"type": "defect", "entry_id": entry.get("id"), "data": deepcopy(defect)},
                action="edit",
            )
        except Exception:
            pass

        extra = defect.get("extra") or {}
        if not isinstance(extra, dict):
            extra = {}

        for k, v in extra_fields.items():
            extra[k] = v

        defect["extra"] = extra
        self.save(update_fields=["history", "updated_at"])
        return True

    def set_qrr_for_defect(self, defect_id: str, responsible: str | None = None, grade: str | None = None, overwrite_main: bool = False, **kwargs) -> bool:
        """
        Удобный метод для QRR: записать ответственного и/или грейд в дефект.
        По умолчанию пишет в defect['extra'] поля: 'qrr_responsible', 'qrr_grade'.
        Если overwrite_main=True и grade задан, дополнительно перезапишет основной defect['grade'].
        Доп.поля можно передать через kwargs (например: qrr_comment, root_cause, ticket).
        """
        zone, post, entry, defect, _ = self.get_defect_by_id(defect_id)
        if defect is None:
            return False

        # backup исходного дефекта
        try:
            VINHistoryBackup.objects.create(
                vin=self.vin,
                post=post,
                zone=zone,
                entry={"type": "defect", "entry_id": entry.get("id"), "data": deepcopy(defect)},
                action="edit",
            )
        except Exception:
            pass

        # запишем в extra
        extra_payload = {}
        if responsible is not None:
            extra_payload["qrr_responsible"] = responsible
        if grade is not None:
            extra_payload["qrr_grade"] = grade
        extra_payload.update(kwargs)

        extra = defect.get("extra") or {}
        if not isinstance(extra, dict):
            extra = {}
        for k, v in extra_payload.items():
            extra[k] = v
        defect["extra"] = extra

        # опционально обновим основной grade
        if overwrite_main and grade is not None:
            defect["grade"] = grade

        self.save(update_fields=["history", "updated_at"])
        return True

    def delete_entry(self, entry_id: str) -> bool:
        """
        Удаляет запись по её ID. Сохраняет бэкап удаляемой записи.
        Возвращает True, если удалено.
        """
        zone, post, entry, entries_list = self.get_entry_by_id(entry_id)
        if entry is None:
            return False

        # backup
        try:
            VINHistoryBackup.objects.create(
                vin=self.vin,
                post=post,
                zone=zone,
                entry=deepcopy(entry),
                action="delete",
            )
        except Exception:
            pass

        # удалить
        try:
            entries_list.remove(entry)
        except ValueError:
            return False

        self.save(update_fields=["history", "updated_at"])
        return True

    def delete_defect(self, defect_id: str) -> bool:
        """
        Удаляет дефект по его ID. Сохраняет бэкап удаляемого дефекта.
        Возвращает True, если удалено.
        """
        zone, post, entry, defect, defects_list = self.get_defect_by_id(defect_id)
        if defect is None:
            return False

        # backup
        try:
            VINHistoryBackup.objects.create(
                vin=self.vin,
                post=post,
                zone=zone,
                entry={"type": "defect", "entry_id": entry.get("id"), "data": deepcopy(defect)},
                action="delete",
            )
        except Exception:
            pass

        # удалить
        try:
            defects_list.remove(defect)
        except ValueError:
            return False

        self.save(update_fields=["history", "updated_at"])
        return True


class CheryVINHistory(models.Model):
    """Отслеживание истории контроля автомобиля"""
    vin = models.CharField(max_length=17, unique=True, verbose_name="VIN номер автомобиля")
    history = models.JSONField(default=dict, verbose_name="История контроля")  # JSON-хранение истории

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата добавления")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Последнее обновление")

    def add_entry(self, post, defects=None, extra_data=None):
        """
        Универсальная функция для добавления осмотра по посту.

        :param post: Объект поста (экземпляр `Post`).
        :param defects: Список дефектов (по умолчанию пусто).
        :param extra_data: Дополнительные данные (например, фото, комментарии).
        """
        if defects is None:
            defects = []
        if extra_data is None:
            extra_data = {}

        # ✅ Получаем название цеха и поста
        zone = post.location  # Должно быть названием цеха
        post_name = post.name  # Должно быть названием поста

        # ❗️Отладка: Проверяем, какие данные передаются в метод
        print(f"📌 Сохраняем данные в зону: {zone} (цех)")
        print(f"📌 Сохраняем данные в пост: {post_name} (пост)")

        # ✅ Проверяем, есть ли уже зона (цех) в истории
        if zone not in self.history:
            self.history[zone] = {}

        # ✅ Проверяем, есть ли уже пост в зоне
        if post_name not in self.history[zone]:
            self.history[zone][post_name] = []

        # ✅ Запись об осмотре
        inspection_data = {
            "defects": defects,
            "extra_data": extra_data,
            "date_added": now().isoformat(),
        }

        # ✅ Добавляем запись в нужный пост
        self.history[zone][post_name].append(inspection_data)
        self.save()


class ChanganVINHistory(models.Model):
    """Отслеживание истории контроля автомобиля"""
    vin = models.CharField(max_length=17, unique=True, verbose_name="VIN номер автомобиля")
    history = models.JSONField(default=dict, verbose_name="История контроля")  # JSON-хранение истории

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата добавления")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Последнее обновление")

    def add_entry(self, post, defects=None, extra_data=None):
        """
        Универсальная функция для добавления осмотра по посту.

        :param post: Объект поста (экземпляр `Post`).
        :param defects: Список дефектов (по умолчанию пусто).
        :param extra_data: Дополнительные данные (например, фото, комментарии).
        """
        if defects is None:
            defects = []
        if extra_data is None:
            extra_data = {}

        # ✅ Получаем название цеха и поста
        zone = post.location  # Должно быть названием цеха
        post_name = post.name  # Должно быть названием поста

        # ❗️Отладка: Проверяем, какие данные передаются в метод
        print(f"📌 Сохраняем данные в зону: {zone} (цех)")
        print(f"📌 Сохраняем данные в пост: {post_name} (пост)")

        # ✅ Проверяем, есть ли уже зона (цех) в истории
        if zone not in self.history:
            self.history[zone] = {}

        # ✅ Проверяем, есть ли уже пост в зоне
        if post_name not in self.history[zone]:
            self.history[zone][post_name] = []

        # ✅ Запись об осмотре
        inspection_data = {
            "defects": defects,
            "extra_data": extra_data,
            "date_added": now().isoformat(),
        }

        # ✅ Добавляем запись в нужный пост
        self.history[zone][post_name].append(inspection_data)
        self.save()


class ContainerHistory(models.Model):
    """История осмотров контейнеров"""
    container_number = models.CharField(max_length=50, unique=True, verbose_name="Номер контейнера")
    history = models.JSONField(default=dict, verbose_name="История осмотров")  # JSON-хранение истории

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    def add_entry(self, post, controller_username, has_defect=None, description="", photos=None, date_added=None):
        """
        Добавляет запись осмотра контейнера в историю.

        :param has_defect: "yes"/"no" или None (если не нужно писать это поле)
        """
        zone = post.location
        post_name = post.name
        if photos is None:
            photos = []

        if zone not in self.history:
            self.history[zone] = {}

        if post_name not in self.history[zone]:
            self.history[zone][post_name] = []

        inspection_entry = {
            "container_number": self.container_number,
            "photos": photos,
            "description": description,
            "date_added": date_added,
            "controller": controller_username,
        }
        # Добавляем ключ только если задан
        if has_defect is not None:
            inspection_entry["has_defect"] = has_defect

        self.history[zone][post_name].append(inspection_entry)
        self.save()

    def str(self):
        return self.container_number


class VINHistoryBackup(models.Model):
    ACTION_CHOICES = [
        ("edit", "Изменено"),
        ("delete", "Удалено"),
    ]

    vin = models.CharField(max_length=17, verbose_name="VIN номер автомобиля")
    post = models.CharField(max_length=255, verbose_name="Название поста")
    zone = models.CharField(max_length=255, verbose_name="Цех")
    entry = models.JSONField(verbose_name="Содержимое записи")
    action = models.CharField(max_length=10, choices=ACTION_CHOICES, verbose_name="Тип действия")
    deleted_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата изменения/удаления")

    def __str__(self):
        return f"{self.vin} — {self.post} — {self.action} — {self.deleted_at.strftime('%Y-%m-%d %H:%M')}"


class AssemblyPassLog(models.Model):
    """
    Фиксация прохождения поста:
    - VIN
    - кто сохранил
    - когда сохранено
    - линия (gwm / chery / changan)
    """
    LINE_CHOICES = [
        ("gwm", "GWM"),
        ("chery", "Chery"),
        ("changan", "Changan"),
    ]

    vin = models.CharField(max_length=17, verbose_name="VIN", db_index=True)
    saved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assembly_pass_logs",
        verbose_name="Кто сохранил"
    )
    scanned_at = models.DateTimeField(auto_now_add=True, verbose_name="Когда сохранено", db_index=True)
    line = models.CharField(
        max_length=20,
        choices=LINE_CHOICES,
        verbose_name="Линия сборки",
        db_index=True
    )

    class Meta:
        verbose_name = "Прохождение поста (скан VIN)"
        verbose_name_plural = "Прохождения поста (сканы VIN)"
        indexes = [
            models.Index(fields=["vin"], name="idx_vin"),
            models.Index(fields=["scanned_at"], name="idx_scanned_at"),
            models.Index(fields=["line"], name="idx_line"),
        ]

    def __str__(self):
        return f"{self.vin} — {self.get_line_display()} — {self.scanned_at:%Y-%m-%d %H:%M}"

    @classmethod
    def record_scan(cls, *, vin: str, user=None, line: str = None):
        """
        Быстрая запись скана VIN.
        Возвращает (obj, created).
        """
        vin = (vin or "").strip().upper()
        obj, created = cls.objects.get_or_create(
            vin=vin,
            defaults={"saved_by": user, "line": line}
        )
        if not created:
            updated = False
            if user and obj.saved_by is None:
                obj.saved_by = user
                updated = True
            if line and not obj.line:
                obj.line = line
                updated = True
            if updated:
                obj.save(update_fields=["saved_by", "line"])
        return obj, created


# -------------------- TrimOutPassLog --------------------
class TrimOutPassLog(models.Model):
    """
    Фиксация выхода из TRIM (trim out):
    - VIN
    - кто сохранил
    - когда сохранено
    - линия (gwm / chery / changan)
    """
    LINE_CHOICES = [
        ("gwm", "GWM"),
        ("chery", "Chery"),
        ("changan", "Changan"),
        ("frame", "Frame"),
    ]

    vin = models.CharField(max_length=17, verbose_name="VIN", db_index=True)
    saved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="trimout_pass_logs",
        verbose_name="Кто сохранил",
    )
    scanned_at = models.DateTimeField(default=timezone.now, verbose_name="Когда сохранено", db_index=True)
    line = models.CharField(
        max_length=20,
        choices=LINE_CHOICES,
        verbose_name="Линия сборки",
        db_index=True,
    )

    class Meta:
        verbose_name = "TRIM OUT (скан VIN)"
        verbose_name_plural = "TRIM OUT (сканы VIN)"
        indexes = [
            models.Index(fields=["vin"], name="idx_trimout_vin"),
            models.Index(fields=["scanned_at"], name="idx_trimout_scanned_at"),
            models.Index(fields=["line"], name="idx_trimout_line"),
        ]

    def __str__(self):
        return f"{self.vin} — {self.get_line_display()} — {self.scanned_at:%Y-%m-%d %H:%M}"

    @classmethod
    def record_scan(cls, *, vin: str, user=None, line: str = None):
        """
        Быстрая запись скана VIN (trim out).
        Возвращает (obj, created).
        По умолчанию допускаем повторные сканы одного VIN, поэтому НЕ используем уникальное ограничение —
        но если нужно хранить только один факт trim out на VIN, замените create на get_or_create(vin=vin,...).
        """
        vin = (vin or "").strip().upper()
        obj, created = cls.objects.get_or_create(
            vin=vin,
            saved_by=user,
            line=line,
            defaults={"scanned_at": timezone.now()},  # чтобы было значение при первом создании
        )
        return obj, True


# -------------------- VESPassLog --------------------
class VESPassLog(models.Model):
    """
    Фиксация передачи VIN на VES и приёма обратно.
    - VIN
    - кто отдал и когда
    - кто принял и когда
    Допускается несколько циклов "отдал/принял" для одного VIN.
    """
    vin = models.CharField(max_length=17, verbose_name="VIN", db_index=True)

    given_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ves_given_logs",
        verbose_name="Кто отдал на VES",
    )
    given_at = models.DateTimeField(
        verbose_name="Дата/время отдачи на VES",
        db_index=True,
    )

    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ves_received_logs",
        verbose_name="Кто принял с VES",
    )
    received_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дата/время приёма с VES",
        db_index=True,
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        verbose_name = "VES: передача/приём VIN"
        verbose_name_plural = "VES: передачи/приёмы VIN"
        indexes = [
            models.Index(fields=["vin"], name="idx_ves_vin"),
            models.Index(fields=["given_at"], name="idx_ves_given_at"),
            models.Index(fields=["received_at"], name="idx_ves_received_at"),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(received_at__gte=models.F("given_at")) | models.Q(received_at__isnull=True),
                name="ves_received_after_given",
            ),
        ]

    def __str__(self):
        status = "закрыт" if self.received_at else "ожидает приёма"
        return f"{self.vin} — отдан: {self.given_at:%Y-%m-%d %H:%M} — {status}"

    @property
    def is_closed(self) -> bool:
        return self.received_at is not None

    @property
    def duration_seconds(self) -> int | None:
        """
        Сколько времени VIN находился/находится на VES.
        Возвращает секунды (int) или None, если нет даты отдачи.
        """
        if not self.given_at:
            return None
        end_dt = self.received_at or now()
        return int((end_dt - self.given_at).total_seconds())

    @classmethod
    def record_give(cls, *, vin: str, user=None, when=None):
        """
        Быстрая запись факта передачи на VES.
        Возвращает созданный объект.
        """
        vin = (vin or "").strip().upper()
        when = when or now()
        return cls.objects.create(vin=vin, given_by=user, given_at=when)

    @classmethod
    def record_receive(cls, *, vin: str, user=None, when=None):
        """
        Быстрая фиксация приема с VES. Ищет последний незакрытый лог по VIN.
        Если найден — проставляет получателя и время.
        Если нет — создаёт новую запись с совпадающими given_at/received_at.
        Возвращает (obj, updated: bool), где updated=True если закрыли существующую запись.
        """
        vin = (vin or "").strip().upper()
        when = when or now()

        # Ищем последний "отдан, но не принят"
        obj = cls.objects.filter(vin=vin, received_at__isnull=True).order_by("-given_at").first()
        if obj:
            obj.received_by = user
            obj.received_at = when
            obj.save(update_fields=["received_by", "received_at", "updated_at"])
            return obj, True

        # Не нашли открытой записи — создаём автолог
        obj = cls(vin=vin, given_at=when, received_at=when)
        if user:
            obj.given_by = user
            obj.received_by = user
        obj.save()
        return obj, False


class VehicleIdentifiers(models.Model):
    vin = models.CharField("VIN код", max_length=17, unique=True, db_index=True)
    engine_number = models.CharField("Номер двигателя", max_length=64, blank=True, null=True)
    transmission_number = models.CharField("Номер трансмиссии", max_length=64, blank=True, null=True)

    saved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто сохранил",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="saved_vehicle_identifiers",
    )

    created_at = models.DateTimeField("Когда сохранили", auto_now_add=True)
    updated_at = models.DateTimeField("Когда обновлена запись", auto_now=True)

    class Meta:
        verbose_name = "Идентификаторы автомобиля"
        verbose_name_plural = "Идентификаторы автомобилей"
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["vin"]),
        ]

    def str(self):
        return f"{self.vin} | Engine: {self.engine_number or '—'} | Trans: {self.transmission_number or '—'}"
