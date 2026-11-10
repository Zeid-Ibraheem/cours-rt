# Format d'un paquet de séance

Un paquet est un zip nommé `seance-AAAA-MM-JJ.zip` (ou `seance-AAAA-MM-JJ-2.zip` s'il y en a plusieurs le même jour). Tout est à plat dedans, sans dossier :

```
seance-2026-11-10.zip
├── seance.json                         ← la description de la séance (obligatoire)
├── 2026-11-10-ospf-bases.md            ← une fiche
├── 2026-11-10-ospf-topologie.png       ← une image utilisée par la fiche
├── 2026-11-10-exo-cout-ospf.md         ← un exercice avec son corrigé
├── 2026-11-10-sujet-ospf-1.pdf         ← un sujet d'entraînement
├── 2026-11-10-sujet-ospf-1.tex         ← sa source
├── 2026-11-10-sujet-ospf-1-corrige.pdf ← son corrigé
└── CM3_OSPF.pdf                        ← un support du prof (reste sur le PC, jamais publié)
```

La commande `cours` range chaque fichier dans `S<semestre>/<ressource>/<type>/`, met à jour `catalogue.json`, refait les sommaires, enregistre et envoie sur GitHub.

## seance.json

```json
{
  "format": 1,
  "date": "2026-11-10",
  "titre": "OSPF : routage dynamique",
  "resume": "Deux à quatre phrases sur ce qu'on a revu et ce qui coinçait encore.",
  "ressources": { "R3.07": "Nom complet de la ressource" },
  "controles": { "R3.07": "2026-11-17" },
  "fichiers": [
    {
      "fichier": "2026-11-10-ospf-bases.md",
      "type": "fiche",
      "titre": "OSPF : les bases",
      "chapitre": "Routage dynamique",
      "annexes": ["2026-11-10-ospf-topologie.png"]
    },
    {
      "fichier": "2026-11-10-exo-cout-ospf.md",
      "type": "exercice",
      "titre": "Calcul des coûts OSPF (d'après TD 3, exo 2)",
      "chapitre": "Routage dynamique"
    },
    {
      "fichier": "2026-11-10-sujet-ospf-1.pdf",
      "type": "entrainement",
      "titre": "Sujet type contrôle n°1",
      "chapitre": "Routage dynamique",
      "source": "2026-11-10-sujet-ospf-1.tex",
      "corrige": "2026-11-10-sujet-ospf-1-corrige.pdf"
    }
  ],
  "pieges": {
    "R3.07": [
      "Le coût OSPF se calcule avec la bande passante de référence (100 Mbit/s par défaut), pas avec le débit réel du lien."
    ]
  },
  "fournis": {
    "R3.07": [ { "fichier": "CM3_OSPF.pdf", "titre": "CM 3 : OSPF" } ]
  }
}
```

| Champ | Obligatoire | Contenu |
|---|---|---|
| `format` | oui | toujours `1` |
| `date` | oui | jour de la séance, `AAAA-MM-JJ` |
| `titre` | oui | le sujet de la séance, court |
| `resume` | non | deux à quatre phrases |
| `ressources` | oui | code → nom complet. Codes : `R3.07`, `SAE3.01`… |
| `controles` | non | code → date du prochain contrôle |
| `fichiers` | non | la liste des fichiers à publier (voir dessous) |
| `pieges` | non | code → liste de phrases : l'erreur faite et la bonne réponse |
| `fournis` | non | code → supports des profs utilisés. Le fichier peut être joint au zip : il est rangé sur le PC, jamais publié |

Pour chaque élément de `fichiers` :

| Champ | Obligatoire | Contenu |
|---|---|---|
| `fichier` | oui | nom du fichier dans le zip |
| `type` | oui | `fiche`, `exercice`, `entrainement` ou `divers` |
| `titre` | oui | ce qui s'affiche dans le sommaire |
| `chapitre` | non | sert à regrouper les fichiers dans le sommaire |
| `ressource` | si plusieurs | code de la ressource ; inutile s'il n'y en a qu'une dans le paquet |
| `source` | non | fichier source (.tex, .md…) d'un PDF |
| `corrige` | non | fichier du corrigé |
| `annexes` | non | images ou fichiers utilisés par le fichier principal, rangés à côté |
| `remplace` | non | `true` pour remplacer une ancienne version du même nom (correction) |

## Règles

- **Noms de fichiers** : minuscules, chiffres, points et tirets, préfixés par la date (`2026-11-10-ospf-bases.md`). `readme.md`, `pieges.md` et `index.md` sont réservés.
- **Extensions acceptées** : md, pdf, tex, png, jpg, jpeg, svg, gif, txt, csv, py, sh, cfg, conf, pkt, json.
- **Taille** : moins de 20 Mo par fichier conseillé ; GitHub refuse au-delà de 100 Mo.
- **Liens internes** : une fiche qui affiche une image la cite par son seul nom (`![topologie](2026-11-10-ospf-topologie.png)`), puisqu'elles sont rangées dans le même dossier.
- **Formules** : `$...$` dans le texte et `$$...$$` sur une ligne à part, GitHub les affiche.
- **Schémas** : un bloc ```` ```mermaid ```` dans le Markdown, ou une image en annexe.
- **Aucune info perso** : la commande bloque l'envoi si un mot de `~/.config/cours-rt/mots_interdits.txt` apparaît, et demande confirmation pour tout ce qui ressemble à un numéro ou une adresse mail.
- **Pas de copie des supports des profs** : on reformule, et on cite la source (« d'après TD 3, exo 2 »).

Si un paquet est refusé, rien n'est modifié : la commande explique pourquoi, et il suffit de redemander un paquet corrigé.
