# 🚀 Plateforme de Prospection Commerciale Mmove Multi-Clients

Bienvenue sur la plateforme cartographique de prospection commerciale **M Move**.  
Cet outil permet de générer en quelques secondes des démonstrations interactives ultra-personnalisées pour **n'importe quel prospect** (automobile, grande distribution, bricolage, immobilier, sport, etc.), afin de démontrer la puissance de frappe et la proximité du réseau des 134 remorques publicitaires Mmove en Wallonie.

---

## 📁 Structure du Projet

```
MDS AI /
│
├── core/
│   ├── mmove_network.csv          # Base officielle des 134 remorques Mmove
│   ├── engine.py                  # Moteur universel de calcul de proximité (Haversine 5/10 km)
│   └── template/                  # Template web moderne & responsive
│       ├── index.html             # Interface interactive (Leaflet + filtres dynamiques)
│       └── logo-mmove.png         # Logo officiel Mmove
│
├── clients/                       # Dossiers par prospect / client
│   ├── _template_client/          # Modèle vierge prêt à dupliquer
│   │   ├── config.json            # Charte graphique & vocabulaire métier
│   │   └── locations.csv          # Adresses ou coordonnées des points du prospect
│   │
│   ├── marjorie-thomas/           # Cas réel Immobilier (133 biens à vendre)
│   ├── exemple-automobile/        # Démo Concessions Automobiles (ex: Peugeot, Opel)
│   └── exemple-retail/            # Démo Grande Distribution (Supermarchés & Drives)
│
├── dist/                          # DÉPLOIEMENTS PRÊTS POUR LE FTP (100% autonomes)
│   ├── marjorie-thomas/index.html
│   ├── groupe-automobile-wallonie/index.html
│   └── supermarches-wallonie/index.html
│
└── generator.py                   # Script de génération en une commande CLI
```

---

## ⚡ Méthode 1 : Créer un Nouveau Prospect via Terminal (en 2 minutes)

### Étape 1 : Dupliquer le dossier modèle
Copiez le dossier `clients/_template_client/` et nommez-le avec le nom du prospect (ex: `clients/brico/`) :
```bash
cp -r clients/_template_client clients/brico
```

### Étape 2 : Éditer `config.json`
Renseignez les informations de la marque :
```json
{
  "client_id": "brico",
  "client_name": "Brico Belgique",
  "client_sector": "Bricolage & Jardin",
  "branding": {
    "primary_color": "#D71920",
    "icon_type": "store" 
  },
  "terminology": {
    "entity_name_plural": "Magasins Brico"
  }
}
```
*Types d'icônes disponibles : `store` (magasin), `car` (concession auto), `cart` (supermarché), `home` (immobilier), `fitness` (sport), `building` (entreprise), `pin` (universel).*

### Étape 3 : Remplir `locations.csv`
Placez simplement vos points d'intérêt dans `clients/brico/locations.csv` :
```csv
id,nom,adresse,ville,latitude,longitude,type
1,Brico Namur,Chaussée de Louvain 180,Namur,50.4821,4.8812,Brico Plan-it
2,Brico Charleroi,Rue de la Station 40,Gosselies,50.4712,4.4398,Brico Standard
```
*(Si vous n'avez pas les coordonnées GPS, ajoutez l'option `--geocode` lors de la commande ci-dessous).*

### Étape 4 : Lancer le générateur
```bash
python3 generator.py --client brico
```
Le dossier autonome est immédiatement créé dans `dist/brico/index.html` !

---

## 🎯 Méthode 2 : Démo Live Directement dans le Navigateur

Vous êtes en rendez-vous client ou en préparation express ?
1. Ouvrez n'importe quelle carte existante dans votre navigateur (ex: `dist/marjorie-thomas/index.html`).
2. Cliquez sur le bouton bleu **« Nouveau Prospect »** en haut à droite.
3. Tapez le nom du client, choisissez sa couleur et son icône.
4. Glissez-déposez un fichier CSV ou collez la liste des adresses.
5. Cliquez sur **« Lancer la Simulation »** : la carte se recalcule et se rebrand instantanément en 50 millisecondes !

---

## 🌐 Déploiement sur un Hébergement Web / Serveur FTP

Tous les dossiers générés dans `dist/` sont **100 % autonomes et statiques** (zéro dépendance PHP, Node.js ou base de données SQL) :
1. Connectez-vous à votre FTP (OVH, Infomaniak, Hostinger, cPanel, etc.).
2. Glissez simplement le dossier de votre choix (ex: `dist/brico/`) sur votre serveur dans `public_html/prospects/brico/`.
3. Votre prospect peut immédiatement visualiser son audit en ligne sur :  
   `https://votre-site.be/prospects/brico/`

---

## 🏆 Argumentaire Commercial Automatique Inclus dans l'Outil

Pour chaque prospect, l'outil calcule et affiche en direct :
- Le **taux de couverture & d'encerclement** :  
  *Ex: "82 % de vos points de vente sont entourés à moins de 5 km par une remorque Mmove"*.
- La **distance moyenne** au panneau le plus proche.
- Le **Top 15 des panneaux Mmove les plus stratégiques** pour ce prospect (onglet *🏆 Top Mmove*).
- Un bouton d'**Export CSV** pour transmettre l'audit chiffré au prospect par e-mail.
