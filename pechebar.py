import requests
from bs4 import BeautifulSoup
import json
import webbrowser
import os
import datetime
import time
import re

# Configuration des ports (identifiants maree.info et coordonnées GPS)
PORTS = [
    {"id": "110", "name": "Pénerf", "lat": 47.50, "lng": -2.62},
    {"id": "108", "name": "Le Croisic", "lat": 47.29, "lng": -2.51},
    {"id": "112", "name": "St Armel (Vannes)", "lat": 47.59, "lng": -2.71},
    {"id": "111", "name": "Le Logeo (Port-Navalo)", "lat": 47.55, "lng": -2.81}
]

# Session globale pour réutiliser la connexion et éviter les erreurs SSL (EOF)
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
    'Referer': 'https://maree.info/'
})

def fetch_weather(lat, lng):
    """Récupère la météo avec un système de retentative en cas de coupure SSL."""
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lng}&daily=weathercode,windspeed_10m_max,precipitation_sum,sunrise,sunset&timezone=Europe%2FParis&forecast_days=10"
    for attempt in range(3):
        try:
            response = session.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"    [ATTENTION] Coupure météo (tentative {attempt+1}/3)...")
            time.sleep(1)
    return None

def fetch_maree_html(port_id, date_obj):
    """Télécharge le calendrier de la semaine à partir d'une date précise."""
    date_param = date_obj.strftime("%Y%m%d")
    url = f"https://maree.info/{port_id}?d={date_param}"
    for attempt in range(3):
        try:
            response = session.get(url, timeout=10)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            print(f"    [ATTENTION] Coupure maree.info (tentative {attempt+1}/3)...")
            time.sleep(1)
    return None

def parse_maree_html(html):
    """Parse le format HTML actuel de maree.info (table MareeJours)."""
    soup = BeautifulSoup(html, 'html.parser')
    tides = []

    maree_jours = soup.find('table', id='MareeJours')
    if not maree_jours:
        print("  [X] Table MareeJours introuvable.")
        return tides

    for row in maree_jours.find_all('tr'):
        if 'MJ' not in row.get('class', []):
            continue

        th = row.find('th')
        if not th:
            continue
        a_tag = th.find('a')
        if not a_tag:
            continue
        # Format URL : ?d=YYYYMMDD + 1 chiffre offset dans la semaine (ex: 202605211 = 22 mai)
        match = re.search(r'\?d=(\d{8})(\d)', a_tag.get('onmouseover', ''))
        if not match:
            continue
        base_date = datetime.datetime.strptime(match.group(1), '%Y%m%d').date()
        date_obj = base_date + datetime.timedelta(days=int(match.group(2)))

        tds = row.find_all('td')
        if len(tds) < 3:
            continue

        time_td = tds[0]
        coef_td = tds[2]

        # Temps : PM dans <b>, BM en texte brut (NavigableString)
        time_entries = []
        for child in time_td.children:
            if hasattr(child, 'name') and child.name == 'b':
                text = child.get_text(strip=True)
                if text:
                    time_entries.append((text, True))   # PM
            elif isinstance(child, str):
                text = child.strip()
                if text and text != '\xa0':
                    time_entries.append((text, False))  # BM

        # Coefficients : PM seulement dans <b>
        pm_coeffs = []
        for child in coef_td.children:
            if hasattr(child, 'name') and child.name == 'b':
                text = child.get_text(strip=True)
                if text.isdigit():
                    pm_coeffs.append(int(text))

        pm_idx = 0
        for time_str, is_pm in time_entries:
            coeff = 0
            if is_pm:
                if pm_idx < len(pm_coeffs):
                    coeff = pm_coeffs[pm_idx]
                pm_idx += 1
            tides.append({
                'date_obj': date_obj,
                'type': 'PM' if is_pm else 'BM',
                'time': time_str,
                'coeff': coeff,
            })

    if tides:
        print(f"  -> {len(tides)} marees extraites ({tides[0]['date_obj']} au {tides[-1]['date_obj']})")
    else:
        print("  [X] Aucune marée extraite de cette page.")

    return tides


def parse_jour_detail_js(js_text, date_obj):
    """Extrait les données de marée depuis la réponse JS de load-maree-jour.php."""
    start = js_text.find('e.innerHTML="')
    if start < 0:
        return []
    start += len('e.innerHTML="')
    fragment = js_text[start:].replace('\\"', '"').replace("\\'", "'")
    end = fragment.find('";')
    if end >= 0:
        fragment = fragment[:end]

    soup = BeautifulSoup(fragment, 'html.parser')
    table = soup.find('table', class_='MareeJourDetail')
    if not table:
        return []

    tides = []
    for row in table.find_all('tr'):
        sepvs = row.find_all('td', class_='SEPV')
        coef_td = row.find('td', class_='Coef')
        if not sepvs or not coef_td:
            continue

        time_td = sepvs[0]

        time_entries = []
        for child in time_td.children:
            if hasattr(child, 'name'):
                if child.name == 'b':
                    text = child.get_text(strip=True)
                    if text:
                        time_entries.append((text, True))   # PM
                elif child.name == 'span':
                    text = child.get_text(strip=True)
                    if text:
                        time_entries.append((text, False))  # BM

        pm_coeffs = []
        for child in coef_td.children:
            if hasattr(child, 'name') and child.name == 'b':
                text = child.get_text(strip=True)
                if text.isdigit():
                    pm_coeffs.append(int(text))

        pm_idx = 0
        for time_str, is_pm in time_entries:
            coeff = 0
            if is_pm:
                if pm_idx < len(pm_coeffs):
                    coeff = pm_coeffs[pm_idx]
                pm_idx += 1
            tides.append({
                'date_obj': date_obj,
                'type': 'PM' if is_pm else 'BM',
                'time': time_str,
                'coeff': coeff,
            })

    return tides


def fetch_extra_tides(port_id, next_week_d0, count=3):
    """Récupère les jours 7 à 7+count-1 via l'API interne load-maree-jour.php."""
    next_week_date = datetime.datetime.strptime(str(next_week_d0), '%Y%m%d').date()
    tides = []
    for j in range(count):
        date_obj = next_week_date + datetime.timedelta(days=j)
        url = f"https://maree.info/do/load-maree-jour.php?p={port_id}&d={next_week_d0}&j={j}"
        for attempt in range(3):
            try:
                response = session.get(url, timeout=10)
                response.raise_for_status()
                day_tides = parse_jour_detail_js(response.text, date_obj)
                if day_tides:
                    print(f"  -> {date_obj} : {len(day_tides)} marees extraites via API")
                    tides.extend(day_tides)
                else:
                    print(f"  [X] {date_obj} : aucune maree extraite via API")
                break
            except requests.RequestException:
                print(f"    [ATTENTION] Echec API jour {j} (tentative {attempt+1}/3)...")
                time.sleep(1)
    return tides


def parse_time_str(time_str):
    time_str = time_str.strip().replace(':', 'h')
    if 'h' in time_str:
        parts = time_str.split('h')
        mins = int(parts[1]) if len(parts) > 1 and parts[1].strip() else 0
        return int(parts[0]) * 60 + mins
    return 0

def get_weather_desc(code):
    if code <= 1:        return "Ensoleillé"
    if code == 2:        return "Peu nuageux"
    if code == 3:        return "Couvert"
    if code in (45, 48): return "Brouillard"
    if 51 <= code <= 57: return "Bruine"
    if 61 <= code <= 67: return "Pluie"
    if 71 <= code <= 77: return "Neige"
    if 80 <= code <= 82: return "Averses"
    if code >= 95:       return "Orage"
    return "Variable"

def format_minutes(minutes_abs):
    minutes_of_day = minutes_abs % 1440
    h = minutes_of_day // 60
    m = minutes_of_day % 60
    return f"{h:02d}h{m:02d}"

def process_port(port):
    print(f"\n{'='*40}\nAnalyse des données pour {port['name']}...\n{'='*40}")
    
    weather = fetch_weather(port['lat'], port['lng'])
    if not weather or 'daily' not in weather:
        print("Météo indisponible, impossible de filtrer.")
        return []

    jours_semaine = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    mois_annee = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]

    all_tides = []

    # Semaine courante (jours 0-6) via la page principale
    print(f"Telechargement de la semaine courante...")
    html = fetch_maree_html(port['id'], datetime.date.today())
    if html:
        page_tides = parse_maree_html(html)
        all_tides.extend(page_tides)

        # Jours 7-9 via l'API interne (la page ne fournit que 7 jours)
        match_dates = re.search(r"'Dates'\s*:\s*\[(\d{8})", html)
        if match_dates:
            week_d0 = match_dates.group(1)
            week_start = datetime.datetime.strptime(week_d0, '%Y%m%d').date()
            next_week_d0 = (week_start + datetime.timedelta(days=7)).strftime('%Y%m%d')
            print(f"Telechargement jours 7-9 via API (semaine du {next_week_d0})...")
            time.sleep(0.5)
            extra = fetch_extra_tides(port['id'], next_week_d0, count=3)
            all_tides.extend(extra)
        else:
            print("  [X] Impossible d'extraire la date de semaine pour les jours 7-9.")

    # Suppression des éventuels doublons (le jour 7 peut se chevaucher)
    unique_tides = []
    seen = set()
    for t in all_tides:
        identifier = f"{t['date_obj']}_{t['time']}_{t['type']}"
        if identifier not in seen:
            seen.add(identifier)
            unique_tides.append(t)

    # Tri chronologique pur
    unique_tides.sort(key=lambda x: (x['date_obj'], parse_time_str(x['time'])))

    slots = []
    last_bm_abs = None
    today_date = datetime.date.today()
    
    print("\n--- Analyse des marées et croisement météo ---")

    for tide in unique_tides:
        day_idx = (tide['date_obj'] - today_date).days
        
        # On se concentre uniquement sur la fenêtre de 10 jours demandée
        if day_idx < 0 or day_idx > 9:
            continue
            
        mins = parse_time_str(tide['time'])
        abs_mins = mins + (day_idx * 1440)
        
        date_label = f"{jours_semaine[tide['date_obj'].weekday()]} {tide['date_obj'].day} {mois_annee[tide['date_obj'].month - 1]}"

        if tide['type'] == 'BM':
            last_bm_abs = abs_mins
            # On n'affiche plus les BM pour ne pas polluer la console

        elif tide['type'] == 'PM':
            if last_bm_abs is None:
                last_bm_abs = abs_mins - (6 * 60 + 12)
                
            pm_abs = abs_mins
            coeff = tide['coeff']
            
            print(f"\n[{date_label}] PM trouvée à {tide['time']} | Coeff: {coeff}")

            try:
                wind = weather['daily']['windspeed_10m_max'][day_idx]
                rain = weather['daily']['precipitation_sum'][day_idx]
            except IndexError:
                print("  [X] Données météo absentes pour ce jour.")
                continue 

            print(f"  -> Météo locale : Vent {wind} km/h | Pluie {rain} mm")
            
            cond_coeff = 50 <= coeff <= 90
            cond_wind = wind < 25
            cond_rain = rain <= 0.2

            if cond_coeff and cond_wind and cond_rain:
                try:
                    sunrise_str = weather['daily']['sunrise'][day_idx].split('T')[1]
                    sunset_str = weather['daily']['sunset'][day_idx].split('T')[1]
                except (IndexError, KeyError):
                    continue
                    
                sunrise_abs = parse_time_str(sunrise_str) + (day_idx * 1440)
                sunset_abs = parse_time_str(sunset_str) + (day_idx * 1440)
                
                # Réduction du créneau aux heures de jour strictes
                start_abs = max(last_bm_abs, sunrise_abs)
                end_abs = min(pm_abs, sunset_abs)
                
                if start_abs < end_abs:
                    print(f"  => SUCCÈS ! Créneau ajouté : {format_minutes(start_abs)} à {format_minutes(end_abs)}")
                    weather_code = weather['daily']['weathercode'][day_idx]
                    activity = 3 if (coeff > 75 and wind < 15) else (2 if coeff > 65 else 1)
                    # Bonus heure dorée : aube ou crépuscule
                    start_tod = start_abs % 1440
                    end_tod = end_abs % 1440
                    if start_tod < 8 * 60 or end_tod > 19 * 60:
                        activity = min(3, activity + 1)

                    slots.append({
                        "portId": port['id'],
                        "date": date_label,
                        "start": format_minutes(start_abs),
                        "end": format_minutes(end_abs),
                        "coeff": coeff,
                        "wind": round(wind),
                        "rain": round(rain, 1),
                        "weather": get_weather_desc(weather_code),
                        "activity": activity
                    })
                else:
                    print(f"  => REJETÉ : La marée montante tombe de nuit.")
            else:
                print(f"  => REJETÉ : Hors critères (Coeff: {'OK' if cond_coeff else 'Echec'}, Vent: {'OK' if cond_wind else 'Echec'}, Pluie: {'OK' if cond_rain else 'Echec'}).")

    return slots

def generate_html(all_slots):
    """Génère le fichier HTML avec les données injectées."""
    
    json_data = json.dumps(all_slots, ensure_ascii=False)
    json_ports = json.dumps(PORTS, ensure_ascii=False)

    html_content = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Prévisions de pêche au bar</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;900&display=swap');
        body {{
            font-family: 'Inter', sans-serif;
            background-color: #f8fafc;
        }}
        .fishing-card {{
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }}
        .fishing-card:hover {{
            transform: translateY(-4px);
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
        }}
    </style>
</head>
<body class="text-slate-800">

    <div id="app" class="max-w-6xl mx-auto px-4 py-12">
        <header class="mb-12 text-center">
            <h1 class="text-4xl font-black text-slate-900 mb-4 tracking-tight">Prévisions de pêche au bar</h1>
            <p class="text-slate-500 font-medium text-sm">Données sur 10 jours extraites de maree.info et Open-Meteo</p>
            
            <div class="mt-8 flex flex-wrap justify-center gap-2" id="port-selector"></div>
        </header>

        <main id="forecast-grid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
            <!-- Rempli par le JavaScript -->
        </main>

        <footer class="mt-24 pt-12 border-t border-slate-200 text-center">
            <div class="inline-block bg-white px-8 py-5 rounded-3xl shadow-sm border border-slate-100">
                <h3 class="text-[10px] font-black text-slate-400 uppercase tracking-[0.2em] mb-4 text-center">Critères strictement appliqués</h3>
                <div class="flex flex-wrap justify-center gap-8 text-xs font-bold text-slate-600">
                    <span class="flex items-center gap-2">
                        <div class="w-1.5 h-1.5 rounded-full bg-blue-500"></div> Coeff entre 60 et 90
                    </span>
                    <span class="flex items-center gap-2">
                        <div class="w-1.5 h-1.5 rounded-full bg-blue-500"></div> Marée montante (coupée au lever/coucher)
                    </span>
                    <span class="flex items-center gap-2">
                        <div class="w-1.5 h-1.5 rounded-full bg-blue-500"></div> Sans pluie et vent modéré (< 25 km/h)
                    </span>
                </div>
            </div>
        </footer>
    </div>

    <script>
        const PORTS = {json_ports};
        const ALL_FORECASTS = {json_data};
        
        let selectedPortId = PORTS[0].id;

        function renderButtons() {{
            document.getElementById('port-selector').innerHTML = PORTS.map(p => `
                <button onclick="selectedPortId='${{p.id}}'; renderButtons(); renderResults();" 
                        class="px-6 py-2.5 rounded-xl text-xs font-black transition-all uppercase tracking-widest ${{selectedPortId === p.id ? 'bg-slate-900 text-white shadow-md' : 'bg-white text-slate-400 border border-slate-200 hover:border-slate-300'}}">
                    ${{p.name}}
                </button>
            `).join('');
        }}

        function renderResults() {{
            const grid = document.getElementById('forecast-grid');
            const portSlots = ALL_FORECASTS.filter(slot => slot.portId === selectedPortId);

            if (portSlots.length === 0) {{
                grid.innerHTML = `<div class="col-span-full text-center py-20 bg-white rounded-[2rem] border-2 border-dashed border-slate-100 text-slate-400 italic">Aucun créneau parfait détecté pour ce port sur les 10 prochains jours.</div>`;
                return;
            }}

            grid.innerHTML = portSlots.map(slot => `
                <div class="fishing-card bg-white rounded-[2rem] p-8 border border-slate-100 shadow-sm flex flex-col justify-between h-full">
                    <div>
                        <div class="flex justify-between items-start mb-8">
                            <span class="text-[10px] font-black text-slate-400 uppercase tracking-widest">${{slot.date}}</span>
                            <div class="bg-slate-900 text-white text-[10px] font-black px-4 py-1.5 rounded-full shadow-lg">COEFF ${{slot.coeff}}</div>
                        </div>
                        
                        <div class="mb-10">
                            <h3 class="text-[10px] font-black text-blue-600 uppercase tracking-widest mb-2">Montante optimale</h3>
                            <div class="text-3xl font-black text-slate-900">${{slot.start}} à ${{slot.end}}</div>
                        </div>
                    </div>

                    <div class="flex items-center justify-between pt-8 border-t border-slate-50 gap-4">
                        <div class="flex flex-col">
                            <span class="text-[9px] font-black text-slate-400 uppercase mb-1">Vent</span>
                            <span class="text-sm font-extrabold text-slate-700">${{slot.wind}} km/h</span>
                        </div>
                        <div class="flex flex-col items-center">
                            <span class="text-[9px] font-black text-slate-400 uppercase mb-1">Pluie</span>
                            <span class="text-sm font-extrabold text-slate-700">${{slot.rain}} mm</span>
                        </div>
                        <div class="flex flex-col items-center">
                            <span class="text-[9px] font-black text-slate-400 uppercase mb-1">Météo</span>
                            <span class="text-xs font-bold text-slate-600">${{slot.weather}}</span>
                        </div>
                        <div class="flex flex-col items-end">
                            <span class="text-[9px] font-black text-slate-400 uppercase mb-2">Activité estimée</span>
                            <div class="flex gap-1">
                                ${{Array(3).fill(0).map((_, i) => `
                                    <svg class="w-5 h-5 ${{i < slot.activity ? 'text-blue-600' : 'text-slate-100'}}" viewBox="0 0 24 24" fill="currentColor"><path d="M22 12c0 1.66-2.01 3-4.5 3-1.05 0-2.01-.24-2.79-.64C13.43 15.22 11.83 16 10 16c-3.31 0-6-2.69-6-6s2.69-6 6-6c1.83 0 3.43.78 4.71 2.64.78-.4 1.74-.64 2.79-.64 2.49 0 4.5 1.34 4.5 3 0 .83-.5 1.58-1.32 2.12.82.54 1.32 1.29 1.32 2.12zM9.5 9a.5.5 0 100-1 .5.5 0 000 1z"/></svg>
                                `).join('')}}
                            </div>
                        </div>
                    </div>
                </div>
            `).join('');
        }}

        // Lancement initial
        renderButtons();
        renderResults();
    </script>
</body>
</html>
"""
    return html_content

def main():
    print("Démarrage du processus de récupération des données...\n")
    all_slots = []
    
    for port in PORTS:
        slots = process_port(port)
        all_slots.extend(slots)
        
    print(f"\n{'='*40}\nExtraction terminée. {len(all_slots)} créneaux trouvés au total.\n{'='*40}")
    
    html_code = generate_html(all_slots)
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    filepath = os.path.join(script_dir, 'index.html')
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html_code)
        
    print(f"Interface générée : {filepath}")
    
    if not os.environ.get('CI'):
        print("Ouverture du navigateur...")
        try:
            browser = webbrowser.get('firefox')
            browser.open('file://' + filepath)
        except webbrowser.Error:
            webbrowser.open('file://' + filepath)

if __name__ == "__main__":
    main()