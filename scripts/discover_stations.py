"""
Script khao sat va tuyen chon 20 thanh pho x >= 2 tram quan trac thuc te
tu OpenAQ API v3 (Viet Nam va Thai Lan - cung mui gio UTC+7).
Uu tien cac tram con hoat dong gan nhat (datetimeLast moi nhat).
Xuat file ket qua ra: config/cities.yaml
"""

import os
import sys
import time
import json
from pathlib import Path
from typing import List, Dict, Any
import requests
import yaml

# Thu muc goc
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
OUTPUT_FILE = CONFIG_DIR / "cities.yaml"

# Load .env
from dotenv import load_dotenv
load_dotenv(dotenv_path=BASE_DIR / ".env")

API_KEY = os.getenv("OPENAQ_API_KEY", "")
BASE_URL = os.getenv("OPENAQ_BASE_URL", "https://api.openaq.org/v3").rstrip("/")
HEADERS = {
    "User-Agent": "OpenAQ-DataWarehouse-Pipeline/2.0",
    "Accept": "application/json",
}
if API_KEY:
    HEADERS["X-API-Key"] = API_KEY


def fetch_country_locations(iso_code: str, max_pages: int = 4) -> List[Dict[str, Any]]:
    """Goi API OpenAQ lay danh sach tram theo quoc gia co co che nghi rate limit."""
    all_locations = []
    for page in range(1, max_pages + 1):
        url = f"{BASE_URL}/locations"
        params = {"iso": iso_code, "limit": 100, "page": page}
        try:
            time.sleep(0.3)
            resp = requests.get(url, headers=HEADERS, params=params, timeout=45)
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                if not results:
                    break
                all_locations.extend(results)
                if len(results) < 100:
                    break
            elif resp.status_code == 429:
                print(f"Rate limit 429 o trang {page}. Tam dung 5 giay...")
                time.sleep(5)
            else:
                print(f"Loi goi {iso_code} page {page}: {resp.status_code}")
                break
        except Exception as e:
            print(f"Loi ket noi: {e}")
            break
    return all_locations


def get_last_datetime(loc: Dict[str, Any]) -> str:
    """Lay chuoi thoi gian cap nhat gan nhat de sap xep."""
    dt_last = loc.get("datetimeLast")
    if isinstance(dt_last, dict):
        return dt_last.get("utc") or ""
    elif isinstance(dt_last, str):
        return dt_last
    return ""


def discover_and_build_registry() -> Dict[str, Any]:
    print("=== BAT DAU KHAO SAT TRAM QUAN TRAC OPENAQ V3 (VN & TH) ===")
    
    # 1. Lay danh sach tram Viet Nam
    print("Dang tai tram quan trac Viet Nam...")
    vn_raw = fetch_country_locations("VN", max_pages=2)
    print(f"-> Thu duoc {len(vn_raw)} tram tai Viet Nam.")

    # 2. Lay danh sach tram Thai Lan
    print("Dang tai tram quan trac Thai Lan...")
    th_raw = fetch_country_locations("TH", max_pages=4)
    print(f"-> Thu duoc {len(th_raw)} tram tai Thai Lan.")

    # 3. Phan loai tram Viet Nam va sap xep theo thoi gian hoat dong moi nhat
    hanoi_stations = []
    hcm_stations = []

    for loc in vn_raw:
        sensors = [s.get("parameter", {}).get("name") for s in loc.get("sensors", [])]
        coords = loc.get("coordinates")
        if not coords or not coords.get("latitude") or not coords.get("longitude"):
            continue
        lat = coords["latitude"]
        lon = coords["longitude"]
        loc_id = loc.get("id")
        name = loc.get("name") or f"Station {loc_id}"
        last_dt = get_last_datetime(loc)
        
        # Loc cac tram co PM2.5 hoac PM10
        if "pm25" in sensors or "pm10" in sensors:
            stn_dict = {
                "station_id": loc_id,
                "station_name": name,
                "latitude": round(lat, 5),
                "longitude": round(lon, 5),
                "last_active": last_dt,
                "sensors": sensors[:4],
            }
            # Ha Noi toa do: 20.8 - 21.4 N, 105.5 - 106.1 E
            if 20.8 <= lat <= 21.4 and 105.5 <= lon <= 106.1:
                hanoi_stations.append(stn_dict)
            # TP. Ho Chi Minh toa do: 10.6 - 11.0 N, 106.5 - 107.0 E
            elif 10.6 <= lat <= 11.0 and 106.5 <= lon <= 107.0:
                hcm_stations.append(stn_dict)

    # Sap xep uu tien tram co du lieu moi nhat
    hanoi_stations.sort(key=lambda x: x["last_active"], reverse=True)
    hcm_stations.sort(key=lambda x: x["last_active"], reverse=True)

    selected_hanoi = hanoi_stations[:4]
    selected_hcm = hcm_stations[:4]
    print(f"-> Chon {len(selected_hanoi)} tram tai Ha Noi (Moi nhat: {selected_hanoi[0]['last_active']}).")
    print(f"-> Chon {len(selected_hcm)} tram tai TP. Ho Chi Minh (Moi nhat: {selected_hcm[0]['last_active']}).")

    # 4. Phan loai tram Thai Lan theo tung thanh pho (locality)
    from collections import defaultdict
    th_city_map = defaultdict(list)
    for loc in th_raw:
        sensors = [s.get("parameter", {}).get("name") for s in loc.get("sensors", [])]
        coords = loc.get("coordinates")
        if not coords or not coords.get("latitude") or not coords.get("longitude"):
            continue
        locality = loc.get("locality")
        if not locality or locality in ("Unknown", "NA", "N/A"):
            continue
        if "pm25" in sensors:
            th_city_map[locality].append({
                "station_id": loc.get("id"),
                "station_name": loc.get("name") or f"Station {loc.get('id')}",
                "latitude": round(coords["latitude"], 5),
                "longitude": round(coords["longitude"], 5),
                "last_active": get_last_datetime(loc),
                "sensors": sensors[:4],
            })

    # Sap xep tung thanh pho Thai Lan theo tram hoat dong moi nhat
    for cname in th_city_map:
        th_city_map[cname].sort(key=lambda x: x["last_active"], reverse=True)

    # Dinh nghia vung mien va toa do trung tam cho 18 thanh pho Thai Lan co tu 2 tram tro len
    th_city_metadata = {
        "Bangkok": {"region": "Trung Thái Lan", "lat": 13.7563, "lon": 100.5018},
        "Rayong": {"region": "Đông Thái Lan", "lat": 12.6814, "lon": 101.2816},
        "Chiang Mai": {"region": "Bắc Thái Lan", "lat": 18.7883, "lon": 98.9853},
        "Mae Hong Son": {"region": "Bắc Thái Lan", "lat": 19.3021, "lon": 97.9654},
        "Samut Prakan": {"region": "Trung Thái Lan", "lat": 13.5991, "lon": 100.5998},
        "Lampang": {"region": "Bắc Thái Lan", "lat": 18.2888, "lon": 99.4928},
        "Chiang Rai": {"region": "Bắc Thái Lan", "lat": 19.9072, "lon": 99.8325},
        "Sisaket": {"region": "Đông Bắc Thái Lan", "lat": 15.1186, "lon": 104.3220},
        "Nonthaburi": {"region": "Trung Thái Lan", "lat": 13.8621, "lon": 100.5144},
        "Samut Sakhon": {"region": "Trung Thái Lan", "lat": 13.5475, "lon": 100.2744},
        "Chon buri": {"region": "Đông Thái Lan", "lat": 13.3611, "lon": 100.9847},
        "Songkhla": {"region": "Nam Thái Lan", "lat": 7.1988, "lon": 100.5951},
        "Yala": {"region": "Nam Thái Lan", "lat": 6.5411, "lon": 101.2813},
        "Saraburi": {"region": "Trung Thái Lan", "lat": 14.5289, "lon": 100.9101},
        "Tak": {"region": "Bắc Thái Lan", "lat": 16.8839, "lon": 99.1258},
        "Lamphun": {"region": "Bắc Thái Lan", "lat": 18.5744, "lon": 99.0087},
        "Bueng Kan": {"region": "Đông Bắc Thái Lan", "lat": 18.3633, "lon": 103.6528},
        "Kalasin": {"region": "Đông Bắc Thái Lan", "lat": 16.4322, "lon": 103.5061},
    }

    cities_list = [
        {
            "city_id": "hanoi",
            "city_name": "Hà Nội",
            "country_code": "VN",
            "country_name": "Việt Nam",
            "region": "Miền Bắc VN",
            "latitude": 21.0285,
            "longitude": 105.8542,
            "stations": selected_hanoi,
        },
        {
            "city_id": "ho_chi_minh",
            "city_name": "TP. Hồ Chí Minh",
            "country_code": "VN",
            "country_name": "Việt Nam",
            "region": "Miền Nam VN",
            "latitude": 10.8231,
            "longitude": 106.6297,
            "stations": selected_hcm,
        },
    ]

    for cname, meta in th_city_metadata.items():
        stns = th_city_map.get(cname, [])
        selected_stns = stns[:3] if len(stns) >= 2 else stns
        display_name = "Chonburi" if cname == "Chon buri" else cname
        cities_list.append({
            "city_id": cname.lower().replace(" ", "_"),
            "city_name": display_name,
            "country_code": "TH",
            "country_name": "Thái Lan",
            "region": meta["region"],
            "latitude": meta["lat"],
            "longitude": meta["lon"],
            "stations": selected_stns,
        })

    registry = {
        "version": "2.0",
        "description": "Danh muc 20 thanh pho va cac tram quan trac thuc te OpenAQ (VN & TH)",
        "target_countries": [
            {"code": "VN", "name": "Việt Nam", "timezone": "Asia/Ho_Chi_Minh"},
            {"code": "TH", "name": "Thái Lan", "timezone": "Asia/Bangkok"},
        ],
        "total_cities": len(cities_list),
        "total_stations": sum(len(c["stations"]) for c in cities_list),
        "cities": cities_list,
    }

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        yaml.dump(registry, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    print(f"=== DA XUAT FILE CAU HINH: {OUTPUT_FILE} ===")
    print(f"Tong so thanh pho: {registry['total_cities']}")
    print(f"Tong so tram quan trac thuc te: {registry['total_stations']}")
    return registry


if __name__ == "__main__":
    discover_and_build_registry()
