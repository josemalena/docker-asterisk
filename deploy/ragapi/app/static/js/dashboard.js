/**
 * dashboard.js
 *
 * Responsabilidades:
 * - Abrir conversaciones
 * - Refrescar listado
 * - Filtros
 * - Estadísticas
 */

(function (global) {
    'use strict';

    const RealIA = global.RealIA || (global.RealIA = {});
    const C = RealIA.conversacion;

    function abrirConversacion(id) {

        if (!C || typeof C.abrir !== 'function') {
            console.error(
                'RealIA.conversacion no disponible'
            );
            return;
        }

        C.abrir(id);
    }

    function bindConversaciones() {

        document
            .querySelectorAll('[data-conv-id]')
            .forEach(function (el) {

                el.addEventListener(
                    'click',
                    function () {

                        abrirConversacion(
                            el.dataset.convId
                        );

                    }
                );

            });

    }

    function bindRefrescar() {

        const btn =
            document.getElementById(
                'btn-refrescar'
            );

        if (!btn)
            return;

        btn.addEventListener(
            'click',
            function () {

                location.reload();

            }
        );

    }

    function bindBuscador() {

        const input =
            document.getElementById(
                'buscar-conversacion'
            );

        if (!input)
            return;

        input.addEventListener(
            'input',
            function () {

                const valor =
                    input.value
                        .toLowerCase()
                        .trim();

                document
                    .querySelectorAll(
                        '[data-conv-id]'
                    )
                    .forEach(function (row) {

                        const texto =
                            row.textContent
                                .toLowerCase();

                        row.style.display =
                            texto.includes(
                                valor
                            )
                                ? ''
                                : 'none';

                    });

            }
        );

    }

    function autoAbrirDesdeQuery() {
        const qs = new URLSearchParams(window.location.search);
        const convId = qs.get('open_conv');
        if (!convId) return;
        abrirConversacion(convId);
    }

    function init() {

        bindConversaciones();
        bindRefrescar();
        bindBuscador();
        autoAbrirDesdeQuery();

        console.log(
            'dashboard.js inicializado'
        );

    }

    if (
        document.readyState ===
        'loading'
    ) {

        document.addEventListener(
            'DOMContentLoaded',
            init
        );

    } else {

        init();

    }

})(window);