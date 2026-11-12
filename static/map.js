/* Xarita: tekshiruvlar (EXIF GPS) va panellar joylashuvi. Leaflet + OpenStreetMap.
   Leaflet yuklanmasa (oflayn), nuqtalar ro'yxat ko'rinishida ko'rsatiladi. */
(() => {
  "use strict";

  const { t, classLabel } = window.I18N;
  const GREEN = "#15803d";
  const RED = "#b91c1c";
  const BLUE = "#2563eb";

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function popupFor(check) {
    const box = el("div", "map-popup");
    box.appendChild(el("strong", null, classLabel(check.predicted_class)));
    box.appendChild(el("div", null, check.filename));
    box.appendChild(el("div", null, `${t("col.loss")}: ~${check.power_loss}%`));
    box.appendChild(el("div", "map-popup__muted", check.created_at));
    return box;
  }

  function fallbackList(container, points) {
    container.innerHTML = "";
    const box = el("div", "map-fallback");
    box.appendChild(el("p", null, t("map.offline")));
    const ul = el("ul");
    points.forEach((p) => ul.appendChild(el("li", null, `${p.label} — ${p.lat.toFixed(5)}, ${p.lon.toFixed(5)}`)));
    box.appendChild(ul);
    container.appendChild(box);
  }

  window.SolarMap = {
    /** data: {checks: [...], panels: [...]} (serverdan) */
    render(container, data) {
      const points = [
        ...data.checks.map((c) => ({ lat: c.lat, lon: c.lon, label: `${classLabel(c.predicted_class)} · ${c.filename}` })),
        ...data.panels.map((p) => ({ lat: p.lat, lon: p.lon, label: p.name })),
      ];

      if (!window.L) {
        fallbackList(container, points);
        return;
      }

      if (!container._map) {
        container._map = window.L.map(container, { scrollWheelZoom: true }).setView([41.3, 64.6], 5);
        window.L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
          maxZoom: 19,
          attribution: "&copy; OpenStreetMap",
        }).addTo(container._map);
        container._layer = window.L.layerGroup().addTo(container._map);
        // Konteyner o'lchami o'zgarsa (tab ochilishi, oyna o'lchami) xarita qayta hisoblanadi
        if (window.ResizeObserver) {
          new ResizeObserver(() => container._map.invalidateSize()).observe(container);
        }
      }
      const { _map: map, _layer: layer } = container;
      layer.clearLayers();

      const bounds = [];
      data.panels.forEach((p) => {
        window.L.circleMarker([p.lat, p.lon], { radius: 11, color: BLUE, weight: 3, fillColor: BLUE, fillOpacity: 0.15 })
          .bindTooltip(p.name, { permanent: false })
          .addTo(layer);
        bounds.push([p.lat, p.lon]);
      });
      data.checks.forEach((c) => {
        window.L.circleMarker([c.lat, c.lon], {
          radius: 7,
          color: "#fff",
          weight: 2,
          fillColor: c.is_clean ? GREEN : RED,
          fillOpacity: 0.95,
        })
          .bindPopup(popupFor(c))
          .addTo(layer);
        bounds.push([c.lat, c.lon]);
      });

      if (bounds.length === 1) map.setView(bounds[0], 15);
      else if (bounds.length > 1) map.fitBounds(bounds, { padding: [40, 40], maxZoom: 16 });
      setTimeout(() => map.invalidateSize(), 50);
    },

    refresh(container) {
      if (container._map) setTimeout(() => container._map.invalidateSize(), 50);
    },
  };
})();
