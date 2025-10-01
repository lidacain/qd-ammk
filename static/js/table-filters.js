$(document).ready(function () {
    var table = $('#inspection-table').DataTable({
        language: {
            url: "/static/vendor/datatables/ru.json"
        },
        order: [],
        initComplete: function () {
            this.api().columns().every(function () {
                var column = this;

                var select = $('<select><option value="">Все</option></select>')
                    .appendTo($(column.header()).empty())
                    .on('change', function () {
                        var val = $.fn.dataTable.util.escapeRegex($(this).val());
                        column.search(val ? '^' + val : '', true, false).draw();
                    });

                var seen = new Set();

                column.data().unique().sort().each(function (d) {
                    // 🔍 Парсим HTML-содержимое ячейки и вытаскиваем только дату (если есть .d-none)
                    var parsed = $('<div>').html(d);
                    if (column.index() === 1) {
                        d = parsed.find(".d-none").text();  // ← получаем YYYY-MM-DD
                    } else {
                        d = parsed.text();  // ← другие колонки — обычный текст
                    }

                    if (d.length > 0 && !seen.has(d)) {
                        seen.add(d);
                        select.append('<option value="' + d + '">' + d + '</option>');
                    }
                });
            });
        }
    });
});