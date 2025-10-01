// 📌 Модальное окно для изображений
let currentGroup = [];
let currentIndex = 0;
let zoomLevel = 1;

function openModal(group, index) {
    currentGroup = group;
    currentIndex = index;
    const modal = document.getElementById("image-modal");
    const modalImg = document.getElementById("modal-img");

    zoomLevel = 1;
    modalImg.style.transform = "scale(1)";
    modalImg.style.cursor = "default";
    modalImg.src = currentGroup[currentIndex];
    modal.style.display = "flex";
}

function closeModal() {
    document.getElementById("image-modal").style.display = "none";
    currentGroup = [];
    currentIndex = 0;
}

function showPrev() {
    if (currentIndex > 0) {
        currentIndex--;
        document.getElementById("modal-img").src = currentGroup[currentIndex];
    }
}

function showNext() {
    if (currentIndex < currentGroup.length - 1) {
        currentIndex++;
        document.getElementById("modal-img").src = currentGroup[currentIndex];
    }
}

function toggleFullScreen() {
    const container = document.getElementById("table-container");
    const isFull = container.classList.toggle("fullscreen-table");

    if (isFull) {
        container.dataset.originalStyle = container.getAttribute("style");
        container.style.position = "fixed";
        container.style.top = "70px";
        container.style.left = "0";
        container.style.right = "0";
        container.style.bottom = "0";
        container.style.zIndex = "9999";
        container.style.background = "#fff";
        container.style.padding = "20px";
        container.style.overflow = "auto";
        container.style.width = "100vw";
        container.style.height = "calc(100vh - 60px)";

        if (!document.getElementById("collapse-btn")) {
            const btn = document.createElement("button");
            btn.innerText = "⬆ Свернуть";
            btn.id = "collapse-btn";
            btn.className = "btn btn-danger position-fixed";
            btn.style.top = "20px";
            btn.style.right = "20px";
            btn.style.zIndex = "10000";
            btn.onclick = toggleFullScreen;
            document.body.appendChild(btn);
        }
    } else {
        container.setAttribute("style", container.dataset.originalStyle);
        const btn = document.getElementById("collapse-btn");
        if (btn) btn.remove();
    }
}

// 📌 Инициализация DataTables с устойчивыми фильтрами
$(document).ready(function () {
    const table = $('#inspection-table');
    if (!table.length) return;

    const dt = table.DataTable({
        scrollX: true,
        scrollY: 'calc(90vh - 250px)',
        scrollCollapse: true,
        orderCellsTop: true,
        fixedHeader: {
            header: true,
            headerOffset: 70
        },
        order: [[1, 'desc']],
        pageLength: 100,
        language: {
            url: "/static/vendor/datatables/ru.json"
        },
        columnDefs: [{
            targets: 0,
            searchable: false,
            orderable: false,
            render: function (data, type, row, meta) {
                return meta.row + 1;
            }
        }],
        initComplete: function () {
            const api = this.api();

            function renderFilters() {
                $('#inspection-table thead tr.filters').remove();

                const filterRow = $('<tr class="filters text-center"></tr>').appendTo($('#inspection-table thead'));

                api.columns().eq(0).each(function (colIdx) {
                    const column = api.column(colIdx);
                    const cell = $('<th></th>').appendTo(filterRow);

                    if ([0, 12, 13].includes(colIdx)) {
                        cell.html('');
                        return;
                    }

                    const select = $('<select class="form-select form-select-sm text-center"><option value="">Все</option></select>')
                        .appendTo(cell)
                        .on('change', function () {
                            const val = $.fn.dataTable.util.escapeRegex($(this).val());
                            column.search(val ? '^' + val + '$' : '', true, false).draw();
                        });

                    column.data().unique().sort().each(function (d) {
                        if (d && d !== 'None') {
                            select.append('<option value="' + d + '">' + d + '</option>');
                        }
                    });

                    // восстановить выбранное значение после redraw
                    const prevValue = column.search().replace(/[\^\$]/g, '');
                    if (prevValue) {
                        select.val(prevValue);
                    }
                });
            }

            renderFilters();

            // при любом обновлении таблицы
            api.on('draw', function () {
                renderFilters();
            });
        }
    });
});

const modalImg = document.getElementById("modal-img");

// 🔍 колесико мыши
modalImg.addEventListener("wheel", function (e) {
    e.preventDefault();
    const zoomStep = 0.1;
    if (e.deltaY < 0) {
        zoomLevel = Math.min(zoomLevel + zoomStep, 3);
    } else {
        zoomLevel = Math.max(zoomLevel - zoomStep, 1);
    }
    this.style.transform = `scale(${zoomLevel})`;
    this.style.cursor = zoomLevel > 1 ? "grab" : "default";
});

// 🔍 двойной клик
modalImg.addEventListener("dblclick", function () {
    zoomLevel = zoomLevel === 1 ? 2 : 1;
    this.style.transform = `scale(${zoomLevel})`;
    this.style.cursor = zoomLevel > 1 ? "grab" : "default";
});