// 地域を確認するための表示範囲。住所入力や位置情報の取得は使用しない。
const areaMapViews = new Map([
    ['平泉地区', {bbox: [141.07, 38.965, 141.15, 39.025], zoom: 13}],
    ['衣川地区', {bbox: [140.94, 39.015, 141.13, 39.085], zoom: 12}],
    ['中尊寺周辺', {bbox: [141.087, 38.991, 141.116, 39.012], zoom: 15}],
    ['平泉駅周辺', {bbox: [141.104, 38.979, 141.13, 38.998], zoom: 15}],
    ['その他・町内全域', {bbox: [141.025, 38.93, 141.25, 39.06], zoom: 12}],
]);

const locationField = document.getElementById('location');
const areaMap = document.getElementById('area-map');
const areaMapCanvas = document.getElementById('area-map-canvas');
const areaMapError = document.getElementById('area-map-error');
const areaMapTitle = document.getElementById('area-map-title');
const areaMapFull = document.getElementById('area-map-full');
let regionMap;
let regionOutline;

function updateAreaMap() {
    const locationName = locationField ? locationField.value : areaMap.dataset.location;
    const view = areaMapViews.get(locationName);
    if (!view) {
        areaMap.hidden = true;
        areaMapFull.removeAttribute('href');
        return;
    }
    const [west, south, east, north] = view.bbox;
    areaMapTitle.textContent = locationName + 'のおおよその地図';
    areaMapCanvas.setAttribute('aria-label', areaMapTitle.textContent);
    areaMapFull.href = 'https://www.openstreetmap.org/#map=' + view.zoom
        + '/' + ((south + north) / 2).toFixed(5)
        + '/' + ((west + east) / 2).toFixed(5);
    areaMap.hidden = false;
    if (!window.L) {
        areaMapError.hidden = false;
        return;
    }
    const bounds = [[south, west], [north, east]];
    if (!regionMap) {
        regionMap = L.map(areaMapCanvas, {scrollWheelZoom: false});
        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>',
        }).on('tileerror', function () {
            areaMapError.hidden = false;
        }).addTo(regionMap);
        regionOutline = L.rectangle(bounds, {
            color: '#d32f2f',
            weight: 4,
            opacity: 1,
            fillColor: '#d32f2f',
            fillOpacity: 0.12,
            interactive: false,
        }).addTo(regionMap);
    } else {
        regionOutline.setBounds(bounds);
    }
    areaMapError.hidden = true;
    regionMap.invalidateSize();
    regionMap.fitBounds(bounds, {padding: [28, 28], maxZoom: 15, animate: false});
}

if (locationField) locationField.addEventListener('change', updateAreaMap);
updateAreaMap();
