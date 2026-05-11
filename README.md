# MossadGlory ext Krogan 🛡️

Mini-extension du projet **MossadGlory** — bot Discord de surveillance des joueurs **Sword** sur **lime.nationsglory.fr**.

---

## Arborescence

```
mossadglory_ext_krogan/
├── main.py                   # Point d'entrée
├── config.py                 # Config centralisée (env vars)
├── requirements.txt
├── .env.example
└── bot/
    ├── cogs/
    │   ├── watchlist.py      # /watchlist add|remove|list
    │   ├── out.py            # /out set|clear
    │   ├── scanner.py        # Boucle scan + live + alertes
    │   ├── admin_config.py   # /config show|set_channel|set_role|set_threshold
    │   └── actions.py        # /actions set|show
    ├── utils/
    │   ├── ng_api.py         # Fetch dynmap NationsGlory
    │   ├── embeds.py         # Tous les embeds Discord
    │   └── checks.py        # Vérifications permissions
    └── database/
        └── db.py             # Couche SQLite async (aiosqlite)
```

---

## Installation

### 1. Prérequis

- Python 3.12+
- pip

### 2. Cloner / copier le dossier

```bash
cd mossadglory_ext_krogan
```

### 3. Installer les dépendances

```bash
pip install -r requirements.txt
```

### 4. Configurer l'environnement

```bash
cp .env.example .env
# Édite .env avec tes valeurs
```

Variables **obligatoires** :
| Variable | Description |
|---|---|
| `DISCORD_TOKEN` | Token du bot Discord |
| `GUILD_ID` | ID de ton serveur Discord |

Variables **recommandées** :
| Variable | Description |
|---|---|
| `CHANNEL_LIVE` | Salon embed live watchlist |
| `CHANNEL_LOGS` | Salon logs connexions |
| `CHANNEL_ALERTS` | Salon alertes actions |
| `ADMIN_ROLES` | IDs rôles admin (virgule-séparés) |
| `NG_SERVER` | Serveur NationsGlory (défaut: `lime`) |

### 5. Lancer le bot

```bash
python main.py
```

---

## Commandes Discord

### Watchlist

| Commande | Description | Permission |
|---|---|---|
| `/watchlist add pseudo` | Ajouter un joueur à surveiller | Admin |
| `/watchlist remove pseudo` | Retirer un joueur | Admin |
| `/watchlist list` | Voir la watchlist | Tout le monde |

### Système OUT

| Commande | Description | Permission |
|---|---|---|
| `/out set pseudo heure` | Marquer OUT (ex: `/out set SwordX 16:30`) | Admin |
| `/out clear pseudo` | Retirer le statut OUT | Admin |

Le OUT est retiré automatiquement quand l'heure configurée arrive.

### Actions

| Commande | Description | Permission |
|---|---|---|
| `/actions set pseudo nombre` | Définir les actions d'un joueur | Admin |
| `/actions show` | Voir les actions de tous | Tout le monde |

### Configuration

| Commande | Description | Permission |
|---|---|---|
| `/config show` | Voir la config actuelle | Admin |
| `/config set_channel type #salon` | Changer un salon | Admin |
| `/config set_role type @role` | Changer un rôle de ping | Admin |
| `/config set_threshold type valeur` | Changer un seuil | Admin |
| `/config reset_live` | Recréer le message live | Admin |

---

## Alertes automatiques

| Seuil | Emoji | Message |
|---|---|---|
| ≥ 2 actions | ⚠️ | Action possible |
| ≥ 3 actions | 🚨 | Infiltration possible |
| ≥ 5 actions | ☢️ | Missile possible |
| Redescend | ✅ | X plus possible |

- Cooldown anti-spam configurable (défaut : 5 min)
- Ping de rôle configurable par type d'alerte

---

## Salon Live

Le salon live affiche un embed auto-updaté toutes les 30s avec :
- 🟢 Joueurs connectés + leurs actions
- 🔴 Joueurs déconnectés
- 🕒 Joueurs OUT avec heure de retour
- ⚡ Total d'actions disponibles

---

## Notes techniques

- **SQLite** : toutes les données persistent dans `bot/database/krogan.db`
- **Cache dynmap** : TTL 20s pour ne pas surcharger l'API NationsGlory
- **Slash commands** : synchronisées sur le guild au démarrage (instantané) ou globalement (1h)
- **Async propre** : aiohttp + aiosqlite, aucun appel bloquant
