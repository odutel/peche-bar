# Prévisions de pêche au bar

Génère une page web avec les meilleurs créneaux de pêche au bar sur 10 jours, en croisant les données de marée (maree.info) et météo (Open-Meteo).

## Page en ligne

**https://odutel.github.io/peche-bar/**

Mise à jour automatique chaque matin à 8h (heure de Paris).

## Critères de sélection d'un créneau

- Coefficient de marée entre 60 et 90
- Marée montante (de la BM vers la PM)
- Vent < 25 km/h
- Pluie ≤ 0,2 mm
- Créneau limité aux heures de jour (lever/coucher du soleil)

## Ports couverts

- Pénerf
- Le Croisic
- St Armel (Vannes)
- Le Logeo (Port-Navalo)

## Installation locale

```bash
pip install -r requirements.txt
python pechebar.py
```

La page s'ouvre automatiquement dans Firefox. Le fichier généré est `index.html`.

## Mise à jour manuelle sur GitHub

Onglet **Actions** du dépôt → workflow "Mise à jour prévisions pêche" → **Run workflow**

## Structure

```
peche-bar/
├── pechebar.py          # Script principal
├── requirements.txt     # requests, beautifulsoup4
├── index.html           # Page générée (commitée par le bot)
├── .github/
│   └── workflows/
│       └── update.yml   # Cron GitHub Actions (8h/jour)
└── .env.example
```

## Variables d'environnement

Aucune clé requise actuellement (maree.info et Open-Meteo sont gratuits et sans auth).
