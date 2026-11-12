#!/usr/bin/env python3
"""cours : range mes séances de révision dans le dépôt et les envoie sur GitHub.

  cours                         importe tous les seance-*.zip de Téléchargements, commit, push
  cours fichier.zip [...]       importe ces paquets-là
  cours ajoute R3.07 a.pdf [...] publie des fichiers que tu as déjà (PDF d'entraînement, fiches…)
                                options : --type entrainement|fiche|exercice|divers  --titre "…"
                                          --chapitre "…"  --date AAAA-MM-JJ  --nom "Nom de la ressource"
                                un dossier à la place des fichiers = tout son contenu
  cours fourni R3.07 cm3.pdf    range un support du prof (liste publiée, fichier jamais publié)
  cours sommaire                refait les pages de sommaire, sans commit
  cours verifie                 contrôle tout le dépôt (infos perso, supports des profs, tailles)
  cours aide                    affiche cette aide

Options : --sans-push (commit sans envoyer)  --oui (ne pose pas de question)
Le format des paquets est décrit dans outils/FORMAT.md.
"""

import datetime as dt
import hashlib
import json
import os
import re
import shutil
import unicodedata
import subprocess
import sys
import zipfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
CATALOGUE = RACINE / "catalogue.json"
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "cours-rt"
MOTS_INTERDITS = CONFIG / "mots_interdits.txt"
TELECHARGEMENTS = Path(os.environ.get("COURS_TELECHARGEMENTS", Path.home() / "Downloads"))
IMPORTES = TELECHARGEMENTS / "cours-rt-importes"

TYPES = {  # type -> (dossier, titre de section, nom au singulier/pluriel)
    "fiche": ("fiches", "Fiches", ("fiche", "fiches")),
    "exercice": ("exercices", "Exercices", ("exercice", "exercices")),
    "entrainement": ("entrainements", "Sujets d'entraînement", ("entraînement", "entraînements")),
    "divers": ("divers", "Divers", ("fichier divers", "fichiers divers")),
}
EXTENSIONS = {"md", "pdf", "tex", "png", "jpg", "jpeg", "svg", "gif", "txt", "csv",
              "py", "sh", "cfg", "conf", "pkt", "json"}
TEXTE = {"md", "tex", "txt", "csv", "py", "sh", "cfg", "conf", "svg", "json"}
NOM_OK = re.compile(r"^[a-z0-9][a-z0-9._-]*\.([a-z0-9]+)$")
RESERVES = {"readme.md", "pieges.md", "index.md"}
MO = 1024 * 1024
LIMITE_DURE = 95 * MO      # GitHub refuse tout fichier de plus de 100 Mio
LIMITE_CONSEIL = 20 * MO

TEL = re.compile(r"(?<!\d)(?:\+33\s?|0)[1-9](?:[ .-]?\d{2}){4}(?!\d)")
MAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
MAILS_EXEMPLES = re.compile(r"@(?:[\w-]+\.)*(example|exemple|test|localhost|domaine|domain|"
                            r"entreprise|societe|iut-exemple|mail)\.", re.I)

OPTIONS = {"sans_push": False, "oui": False}


class Erreur(Exception):
    pass


# ---------------------------------------------------------------- petits outils

def dire(msg=""):
    print(msg, flush=True)


def attention(msg):
    print(f"  ! {msg}", flush=True)


def demander(question):
    if OPTIONS["oui"]:
        return True
    try:
        return input(f"{question} [o/N] ").strip().lower() in ("o", "oui", "y", "yes")
    except EOFError:
        return False


def sha256(donnees):
    return hashlib.sha256(donnees).hexdigest()


def date_fr(iso):
    try:
        return dt.date.fromisoformat(iso).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return iso or ""


def cellule(texte):
    return str(texte or "").replace("|", "\\|").replace("\n", " ").strip()


def pluriel(n, mots):
    return f"{n} {mots[0] if n == 1 else mots[1]}"


def git(*args, verifier=True):
    r = subprocess.run(["git", *args], cwd=RACINE, capture_output=True, text=True)
    if verifier and r.returncode != 0:
        raise Erreur(f"git {' '.join(args)} a échoué :\n{r.stderr.strip()}")
    return r


def normaliser_code(code):
    c = str(code).strip().upper().replace("SAÉ", "SAE").replace(" ", "")
    m = re.fullmatch(r"(R|SAE)([1-6])\.[A-Z0-9]+(?:\.[A-Z0-9]+)*", c)
    if not m:
        raise Erreur(f"code de ressource invalide : « {code} » (attendu : R3.07, SAE3.01…)")
    return c, int(m.group(2))


def dossier_ressource(code):
    code, semestre = normaliser_code(code)
    return Path(f"S{semestre}") / code


def date_valide(texte, quoi):
    try:
        return dt.date.fromisoformat(str(texte)).isoformat()
    except ValueError:
        raise Erreur(f"{quoi} : date invalide « {texte} » (attendu AAAA-MM-JJ)")


# ---------------------------------------------------------------- catalogue

def charger_catalogue():
    if CATALOGUE.exists():
        cat = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    else:
        cat = {}
    for cle, defaut in (("version", 1), ("ressources", {}), ("seances", []),
                        ("fichiers", {}), ("pieges", {}), ("fournis", {})):
        cat.setdefault(cle, defaut)
    return cat


def sauver_catalogue(cat):
    CATALOGUE.write_text(json.dumps(cat, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                         encoding="utf-8")


# ---------------------------------------------------------------- infos perso

def mots_interdits():
    if not MOTS_INTERDITS.exists():
        CONFIG.mkdir(parents=True, exist_ok=True)
        lignes = ["# Un mot ou une expression par ligne. Si l'un d'eux apparaît dans un fichier",
                  "# à publier, l'envoi est bloqué. Ce fichier reste sur ton PC, hors du dépôt.",
                  "# Ajoute : ton nom, ton prénom, ton numéro, ton adresse mail, ton groupe…"]
        for cle in ("user.name", "user.email"):
            v = git("config", "--get", cle, verifier=False).stdout.strip()
            if v:
                lignes.append(v)
        MOTS_INTERDITS.write_text("\n".join(lignes) + "\n", encoding="utf-8")
        attention(f"liste des mots interdits créée : {MOTS_INTERDITS}")
        attention("ajoute-y ton nom, ton numéro, ton mail (nano ~/.config/cours-rt/mots_interdits.txt)")
    mots = []
    for ligne in MOTS_INTERDITS.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if ligne and not ligne.startswith("#"):
            mots.append(ligne)
    return mots


def motif_mot(mot):
    m = re.escape(mot).replace(r"\ ", r"\s+")
    debut = r"(?<!\w)" if mot[:1].isalnum() else ""
    fin = r"(?!\w)" if mot[-1:].isalnum() else ""
    return re.compile(debut + m + fin, re.I)


_PDFTOTEXT = shutil.which("pdftotext")
_PREVENU_PDF = [False]


def texte_de(nom, donnees):
    ext = nom.rsplit(".", 1)[-1].lower()
    if ext in TEXTE:
        return donnees.decode("utf-8", errors="replace")
    if ext == "pdf":
        if not _PDFTOTEXT:
            if not _PREVENU_PDF[0]:
                attention("pdftotext absent : le texte des PDF n'est pas vérifié (sudo pacman -S poppler)")
                _PREVENU_PDF[0] = True
            return ""
        r = subprocess.run([_PDFTOTEXT, "-q", "-", "-"], input=donnees, capture_output=True)
        return r.stdout.decode("utf-8", errors="replace")
    return ""


def scanner(elements):
    """elements : liste de (nom affiché, octets). Renvoie (bloquants, avertissements)."""
    motifs = [(m, motif_mot(m)) for m in mots_interdits()]
    bloquants, avert = [], []
    for nom, donnees in elements:
        texte = texte_de(nom, donnees)
        if not texte:
            continue
        for mot, motif in motifs:
            if motif.search(texte):
                bloquants.append(f"{nom} contient « {mot} »")
        for t in sorted(set(TEL.findall(texte))):
            avert.append(f"{nom} : numéro de téléphone ? « {t} »")
        for m in sorted(set(MAIL.findall(texte))):
            if not MAILS_EXEMPLES.search(m + "."):
                avert.append(f"{nom} : adresse mail ? « {m} »")
    return bloquants, avert


def controle_perso(elements):
    bloquants, avert = scanner(elements)
    if bloquants:
        raise Erreur("info perso trouvée, rien n'est envoyé :\n  - " + "\n  - ".join(bloquants))
    if avert:
        dire("À vérifier (souvent des exemples de cours, mais pas toujours) :")
        for a in avert:
            attention(a)
        if not demander("Ce ne sont pas des infos perso, je continue ?"):
            raise Erreur("arrêté à ta demande, rien n'est envoyé.")


# ---------------------------------------------------------------- lecture d'un paquet

def lire_paquet(chemin):
    chemin = Path(chemin).expanduser()
    if not chemin.is_file():
        raise Erreur(f"fichier introuvable : {chemin}")
    try:
        z = zipfile.ZipFile(chemin)
    except zipfile.BadZipFile:
        raise Erreur(f"{chemin.name} n'est pas un zip valide")
    with z:
        membres = [i for i in z.infolist() if not i.is_dir()
                   and "__MACOSX" not in i.filename and not i.filename.endswith(".DS_Store")]
        noms = [m.filename for m in membres]
        # un paquet zippé avec son dossier : on enlève ce dossier commun
        prefixe = ""
        if noms and all("/" in n for n in noms):
            tetes = {n.split("/", 1)[0] for n in noms}
            if len(tetes) == 1:
                prefixe = tetes.pop() + "/"
        fichiers, total = {}, 0
        for m in membres:
            nom = m.filename[len(prefixe):]
            if nom.startswith("/") or "\\" in nom or ".." in nom.split("/") or "/" in nom:
                raise Erreur(f"{chemin.name} : chemin refusé dans le zip « {m.filename} » "
                             "(les fichiers doivent être à plat, sans dossier)")
            if m.file_size > LIMITE_DURE:
                raise Erreur(f"{nom} fait {m.file_size // MO} Mo : GitHub refuse au-delà de 100 Mo")
            total += m.file_size
            if total > 300 * MO:
                raise Erreur(f"{chemin.name} : paquet trop gros (plus de 300 Mo)")
            fichiers[nom] = z.read(m)
    if "seance.json" not in fichiers:
        raise Erreur(f"{chemin.name} : pas de seance.json dans le paquet")
    try:
        manifeste = json.loads(fichiers.pop("seance.json").decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise Erreur(f"{chemin.name} : seance.json illisible ({e})")
    empreinte = sha256(json.dumps(manifeste, sort_keys=True).encode()
                       + b"".join(sha256(fichiers[n]).encode() for n in sorted(fichiers)))
    return manifeste, fichiers, empreinte


def preparer(manifeste, fichiers, cat):
    """Vérifie tout le paquet et renvoie le plan d'écriture, sans rien toucher."""
    if manifeste.get("format") != 1:
        raise Erreur("seance.json : \"format\" doit valoir 1")
    date = date_valide(manifeste.get("date"), "date de la séance")
    titre = str(manifeste.get("titre") or "").strip()
    if not titre:
        raise Erreur("seance.json : \"titre\" manquant")

    ressources = {}
    for code, nom in (manifeste.get("ressources") or {}).items():
        c, _ = normaliser_code(code)
        ressources[c] = str(nom or "").strip()
    if not ressources:
        raise Erreur("seance.json : au moins une ressource dans \"ressources\"")
    defaut = next(iter(ressources)) if len(ressources) == 1 else None

    def code_de(valeur, ou):
        if valeur in (None, ""):
            if defaut:
                return defaut
            raise Erreur(f"{ou} : \"ressource\" manquante (plusieurs ressources dans le paquet)")
        c, _ = normaliser_code(valeur)
        if c not in ressources and c not in cat["ressources"]:
            raise Erreur(f"{ou} : ressource {c} absente de \"ressources\"")
        return c

    a_ecrire, entrees, utilises, deja_la = [], [], set(), []

    def placer(nom, code, dossier, remplace, ou):
        if nom not in fichiers:
            raise Erreur(f"{ou} : « {nom} » n'est pas dans le zip")
        m = NOM_OK.match(nom)
        if not m or m.group(1) not in EXTENSIONS:
            raise Erreur(f"{ou} : nom refusé « {nom} » (minuscules, chiffres, tirets ; "
                         f"extensions : {', '.join(sorted(EXTENSIONS))})")
        if nom in RESERVES:
            raise Erreur(f"{ou} : le nom « {nom} » est réservé aux pages de sommaire")
        relatif = (dossier_ressource(code) / dossier / nom).as_posix()
        cible = RACINE / relatif
        donnees = fichiers[nom]
        if len(donnees) > LIMITE_CONSEIL:
            attention(f"{nom} fait {len(donnees) // MO} Mo, c'est lourd pour un dépôt Git")
        if cible.exists():
            if sha256(cible.read_bytes()) == sha256(donnees):
                deja_la.append(relatif)
            elif not remplace:
                raise Erreur(f"{relatif} existe déjà avec un autre contenu. "
                             "Renomme le fichier, ou mets \"remplace\": true pour une correction.")
            else:
                a_ecrire.append((relatif, donnees))
        else:
            a_ecrire.append((relatif, donnees))
        utilises.add(nom)
        return relatif

    for i, f in enumerate(manifeste.get("fichiers") or [], 1):
        ou = f"fichiers n°{i}"
        if not isinstance(f, dict) or not f.get("fichier"):
            raise Erreur(f"{ou} : \"fichier\" manquant")
        type_ = f.get("type")
        if type_ not in TYPES:
            raise Erreur(f"{ou} : type « {type_} » inconnu ({', '.join(TYPES)})")
        code = code_de(f.get("ressource"), ou)
        dossier = TYPES[type_][0]
        remplace = bool(f.get("remplace"))
        principal = placer(f["fichier"], code, dossier, remplace, ou)
        entree = {"chemin": principal, "type": type_, "ressource": code, "date": date,
                  "titre": str(f.get("titre") or f["fichier"]).strip(),
                  "chapitre": str(f.get("chapitre") or "").strip(), "remplace": remplace}
        for cle in ("source", "corrige"):
            if f.get(cle):
                entree[cle] = placer(f[cle], code, dossier, remplace, f"{ou} ({cle})")
        annexes = f.get("annexes") or []
        if not isinstance(annexes, list):
            raise Erreur(f"{ou} : \"annexes\" doit être une liste")
        entree["annexes"] = [placer(a, code, dossier, remplace, f"{ou} (annexe)") for a in annexes]
        entrees.append(entree)

    fournis = []  # (code, fichier, titre, octets ou None)
    for code, liste in (manifeste.get("fournis") or {}).items():
        c = code_de(code, "fournis")
        for x in liste or []:
            nom = Path(str(x.get("fichier") or "")).name
            if not nom:
                raise Erreur(f"fournis {c} : \"fichier\" manquant")
            fournis.append((c, nom, str(x.get("titre") or nom).strip(), fichiers.get(nom)))
            if nom in fichiers:
                utilises.add(nom)

    pieges = {}
    for code, liste in (manifeste.get("pieges") or {}).items():
        c = code_de(code, "pieges")
        pieges[c] = [str(p).strip() for p in (liste or []) if str(p).strip()]

    controles = {}
    for code, d in (manifeste.get("controles") or {}).items():
        controles[code_de(code, "controles")] = date_valide(d, f"contrôle {code}")

    for nom in sorted(set(fichiers) - utilises):
        attention(f"{nom} est dans le zip mais n'est cité nulle part dans seance.json : ignoré")

    # contrôle des infos perso : fichiers publiés + textes qui iront dans les sommaires
    textes = json.dumps({"titre": titre, "resume": manifeste.get("resume"), "pieges": pieges,
                         "fichiers": [(e["titre"], e["chapitre"]) for e in entrees],
                         "fournis": [(f[1], f[2]) for f in fournis]}, ensure_ascii=False)
    controle_perso([(r, d) for r, d in a_ecrire] + [("seance.json", textes.encode())])

    return {"date": date, "titre": titre, "resume": str(manifeste.get("resume") or "").strip(),
            "ressources": ressources, "a_ecrire": a_ecrire, "entrees": entrees,
            "fournis": fournis, "pieges": pieges, "controles": controles, "deja_la": deja_la}


def appliquer(plan, cat, empreinte, seance=True):
    for code, nom in plan["ressources"].items():
        r = cat["ressources"].setdefault(code, {"nom": "", "controles": []})
        if nom and not r.get("nom"):
            r["nom"] = nom
    for code, d in plan["controles"].items():
        r = cat["ressources"].setdefault(code, {"nom": "", "controles": []})
        if d not in r["controles"]:
            r["controles"] = sorted(r["controles"] + [d])
    for relatif, donnees in plan["a_ecrire"]:
        cible = RACINE / relatif
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_bytes(donnees)
    for e in plan["entrees"]:
        ancien = cat["fichiers"].get(e["chemin"])
        remplace = e.pop("remplace")
        if ancien and remplace:
            e["date"] = ancien.get("date", e["date"])
            e["maj"] = plan["date"]
        cat["fichiers"][e["chemin"]] = e
    for code, nom, titre, donnees in plan["fournis"]:
        liste = cat["fournis"].setdefault(code, [])
        if not any(x["fichier"] == nom for x in liste):
            liste.append({"fichier": nom, "titre": titre, "date": plan["date"]})
        if donnees is not None:
            cible = RACINE / dossier_ressource(code) / "fournis" / nom
            cible.parent.mkdir(parents=True, exist_ok=True)
            cible.write_bytes(donnees)
    for code, liste in plan["pieges"].items():
        existants = cat["pieges"].setdefault(code, [])
        for p in liste:
            if not any(x["texte"] == p for x in existants):
                existants.append({"date": plan["date"], "texte": p})
    if not seance:
        return
    n = sum(1 for s in cat["seances"] if s["date"] == plan["date"]) + 1
    cat["seances"].append({"id": f"{plan['date']}-{n}", "date": plan["date"], "titre": plan["titre"],
                           "resume": plan["resume"], "ressources": sorted(plan["ressources"]),
                           "fichiers": [e["chemin"] for e in plan["entrees"]],
                           "pieges": sum(len(v) for v in plan["pieges"].values()),
                           "empreinte": empreinte})
    cat["seances"].sort(key=lambda s: (s["date"], s["id"]))


def message_commit(plan):
    compte = {}
    for e in plan["entrees"]:
        compte[e["type"]] = compte.get(e["type"], 0) + 1
    morceaux = [pluriel(compte[t], TYPES[t][2]) for t in TYPES if t in compte]
    n_pieges = sum(len(v) for v in plan["pieges"].values())
    if n_pieges:
        morceaux.append(pluriel(n_pieges, ("piège", "pièges")))
    codes = ", ".join(sorted(plan["ressources"]))
    detail = ", ".join(morceaux) if morceaux else "séance notée"
    return f"{codes} · {plan['titre']} ({detail})"


# ---------------------------------------------------------------- pages générées

def prochain_controle(r):
    aujourd_hui = dt.date.today().isoformat()
    futurs = [d for d in r.get("controles", []) if d >= aujourd_hui]
    return min(futurs) if futurs else ""


def lien(depuis, vers, texte):
    rel = os.path.relpath(RACINE / vers, (RACINE / depuis).parent)
    return f"[{cellule(texte)}]({Path(rel).as_posix()})"


def page_ressource(code, cat):
    r = cat["ressources"].get(code, {})
    dossier = dossier_ressource(code)
    page = (dossier / "README.md").as_posix()
    nom = r.get("nom") or "nom à compléter"
    L = [f"# {code} · {nom}", "", lien(page, "README.md", "← Retour au sommaire"), ""]
    ctrl = prochain_controle(r)
    if ctrl:
        L.append(f"**Prochain contrôle : {date_fr(ctrl)}**  ")
    n_p = len(cat["pieges"].get(code, []))
    L.append(f"À relire en premier avant un contrôle : {lien(page, (dossier / 'pieges.md').as_posix(), 'mes pièges')} ({n_p}).")
    fichiers = [e for e in cat["fichiers"].values() if e["ressource"] == code]
    for type_, (_, section, _) in TYPES.items():
        liste = sorted((e for e in fichiers if e["type"] == type_),
                       key=lambda e: (e.get("chapitre", ""), e["date"], e["titre"]))
        if not liste:
            continue
        L += ["", f"## {section}", ""]
        avec_corrige = any(e.get("corrige") for e in liste)
        avec_source = any(e.get("source") for e in liste)
        tete = ["Chapitre", "Titre", "Date"] + (["Corrigé"] if avec_corrige else []) \
            + (["Source"] if avec_source else [])
        L += ["| " + " | ".join(tete) + " |", "|" + "---|" * len(tete)]
        for e in liste:
            ligne = [cellule(e.get("chapitre")), lien(page, e["chemin"], e["titre"]),
                     date_fr(e["date"]) + (f" (corrigé le {date_fr(e['maj'])})" if e.get("maj") else "")]
            if avec_corrige:
                ligne.append(lien(page, e["corrige"], "corrigé") if e.get("corrige") else "")
            if avec_source:
                ligne.append(lien(page, e["source"], "source") if e.get("source") else "")
            L.append("| " + " | ".join(ligne) + " |")
    fournis = cat["fournis"].get(code, [])
    if fournis:
        L += ["", "## Supports des profs", "",
              "Ils restent sur mon PC : je les liste pour savoir sur quoi s'appuient les fiches, "
              "mais je ne les publie pas.", ""]
        L += [f"- {cellule(f['titre'])} (`{f['fichier']}`)" for f in sorted(fournis, key=lambda f: f["fichier"])]
    seances = [s for s in cat["seances"] if code in s["ressources"]]
    if seances:
        L += ["", "## Séances", ""]
        for s in reversed(seances):
            journal = "journal/" + s["date"] + ".md"
            L.append(f"- {date_fr(s['date'])} · {lien(page, journal, s['titre'])}")
    return "\n".join(L) + "\n"


def page_pieges(code, cat):
    r = cat["ressources"].get(code, {})
    page = (dossier_ressource(code) / "pieges.md").as_posix()
    L = [f"# {code} · Pièges", "", lien(page, (dossier_ressource(code) / "README.md").as_posix(),
                                         f"← Retour à {code}"), "",
         "Les erreurs que j'ai faites en révisant, avec la bonne réponse. "
         "C'est ce que je relis la veille du contrôle.", ""]
    ctrl = prochain_controle(r)
    if ctrl:
        L += [f"Prochain contrôle : {date_fr(ctrl)}", ""]
    pieges = sorted(cat["pieges"].get(code, []), key=lambda p: p["date"], reverse=True)
    L += [f"- **{date_fr(p['date'])}** · {p['texte']}" for p in pieges] or ["Rien pour l'instant."]
    return "\n".join(L) + "\n"


def page_journal(date, cat):
    page = f"journal/{date}.md"
    L = [f"# Révisions du {date_fr(date)}", "", lien(page, "README.md", "← Retour au sommaire")]
    for s in (x for x in cat["seances"] if x["date"] == date):
        L += ["", f"## {s['titre']} · {', '.join(s['ressources'])}", ""]
        if s.get("resume"):
            L += [s["resume"], ""]
        ajoutes = [cat["fichiers"][c] for c in s["fichiers"] if c in cat["fichiers"]]
        if ajoutes:
            L.append("Ajouté :")
            L += [f"- {TYPES[e['type']][2][0].capitalize()} : {lien(page, e['chemin'], e['titre'])}" for e in ajoutes]
        pieges = [(c, p) for c, liste in cat["pieges"].items() for p in liste
                  if p["date"] == date and c in s["ressources"]]
        if pieges:
            L += ["", "Pièges notés :"]
            L += [f"- {c} · {p['texte']}" for c, p in pieges]
    return "\n".join(L) + "\n"


def page_accueil(cat):
    L = ["# Cours R&T : mes révisions", "",
         "Je suis en deuxième année de BUT Réseaux & Télécoms. Je révise mes contrôles avec Claude, "
         "une IA, et tout ce qu'on produit pendant ces séances arrive ici : les explications "
         "remises au propre, les exercices corrigés et les sujets d'entraînement. "
         "J'ajoute une séance à chaque fois que je révise.", "",
         "Les supports des profs restent sur mon PC. Ils sont listés pour savoir sur quoi "
         "s'appuie chaque fiche, mais ils ne sont pas publiés.", "", "## Où j'en suis", ""]
    codes = sorted(cat["ressources"], key=lambda c: (normaliser_code(c)[1], c.startswith("SAE"), c))
    if not codes:
        L.append("Pas encore de séance : la première arrive bientôt.")
    else:
        L += ["| Ressource | Séances | Dernière | Prochain contrôle | Fiches | Exos | Sujets | Pièges |",
              "|---|---|---|---|---|---|---|---|"]
        for c in codes:
            r = cat["ressources"][c]
            seances = [s for s in cat["seances"] if c in s["ressources"]]
            f = [e for e in cat["fichiers"].values() if e["ressource"] == c]
            nb = lambda t: sum(1 for e in f if e["type"] == t) or ""
            titre = f"{c} · {r.get('nom') or 'nom à compléter'}"
            L.append("| " + " | ".join([
                lien("README.md", (dossier_ressource(c) / "README.md").as_posix(), titre),
                str(len(seances) or ""), date_fr(seances[-1]["date"]) if seances else "",
                date_fr(prochain_controle(r)), str(nb("fiche")), str(nb("exercice")),
                str(nb("entrainement")), str(len(cat["pieges"].get(c, [])) or "")]) + " |")
    if cat["seances"]:
        L += ["", "## Dernières séances", ""]
        for s in list(reversed(cat["seances"]))[:8]:
            L.append(f"- {date_fr(s['date'])} · {', '.join(s['ressources'])} · "
                     f"{lien('README.md', 'journal/' + s['date'] + '.md', s['titre'])}")
    L += ["", "## Comment c'est rangé", "",
          "- `S3/R3.07/` : une ressource, avec ses `fiches/`, `exercices/`, `entrainements/` "
          "et `pieges.md`, la liste de mes erreurs.",
          "- `journal/` : une page par jour de révision.",
          "- `outils/` : le script qui range chaque séance et l'envoie ici "
          "([format des paquets](outils/FORMAT.md)).", "",
          "Les formules s'affichent directement sur GitHub. Les sujets d'entraînement sont en PDF, "
          "avec leur source à côté pour pouvoir les corriger."]
    return "\n".join(L) + "\n"


def ecrire_si_change(relatif, contenu):
    cible = RACINE / relatif
    if cible.exists() and cible.read_text(encoding="utf-8") == contenu:
        return
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_text(contenu, encoding="utf-8")


def generer(cat):
    ecrire_si_change("README.md", page_accueil(cat))
    codes = set(cat["ressources"]) | {e["ressource"] for e in cat["fichiers"].values()}
    for code in codes:
        cat["ressources"].setdefault(code, {"nom": "", "controles": []})
        d = dossier_ressource(code)
        ecrire_si_change((d / "README.md").as_posix(), page_ressource(code, cat))
        ecrire_si_change((d / "pieges.md").as_posix(), page_pieges(code, cat))
    for date in sorted({s["date"] for s in cat["seances"]}):
        ecrire_si_change(f"journal/{date}.md", page_journal(date, cat))


# ---------------------------------------------------------------- git

def depot_git():
    r = git("rev-parse", "--show-toplevel", verifier=False)
    if r.returncode != 0 or Path(r.stdout.strip()).resolve() != RACINE:
        raise Erreur(f"{RACINE} n'est pas un dépôt Git. Lance d'abord : cd {RACINE} && git init -b main")


def commit(message):
    git("add", "-A")
    indexes = git("diff", "--cached", "--name-only", "-z").stdout.split("\0")
    indexes = [p for p in indexes if p]
    fuite = [p for p in indexes if "/fournis/" in p]
    if fuite:
        git("reset", "-q", "--", *fuite)
        raise Erreur("un support de prof allait partir sur GitHub, retiré de l'envoi :\n  - "
                     + "\n  - ".join(fuite) + "\nVérifie le .gitignore.")
    if not indexes:
        dire("  Rien de nouveau à enregistrer.")
        return False
    for p in indexes:
        chemin = RACINE / p
        if chemin.is_file() and chemin.stat().st_size > LIMITE_DURE:
            git("reset", "-q", "--", p)
            raise Erreur(f"{p} dépasse 95 Mo : GitHub le refuserait.")
    git("commit", "-q", "-m", message)
    dire(f"  Enregistré : {message}")
    return True


def pousser():
    if OPTIONS["sans_push"]:
        dire("Pas d'envoi (--sans-push). Pour envoyer plus tard : git push")
        return
    dire("Envoi sur GitHub…")
    r = git("push", "-q", verifier=False)
    if r.returncode != 0:
        if "no upstream" in r.stderr or "has no upstream" in r.stderr:
            r = git("push", "-q", "-u", "origin", "HEAD", verifier=False)
        if r.returncode != 0:
            raise Erreur("l'envoi a échoué (tout est bien enregistré sur ton PC) :\n" + r.stderr.strip())
    dire("Envoyé.")


# ---------------------------------------------------------------- commandes

def cmd_importer(chemins):
    depot_git()
    automatique = not chemins
    if automatique:
        chemins = sorted(TELECHARGEMENTS.glob("seance-*.zip"))
        if not chemins:
            dire(f"Aucun paquet seance-*.zip dans {TELECHARGEMENTS}.")
            return 0
    paquets, erreurs = [], 0
    for c in chemins:
        try:
            m, f, emp = lire_paquet(c)
            paquets.append((str(m.get("date", "")), Path(c).expanduser(), m, f, emp))
        except Erreur as e:
            erreurs += 1
            dire(f"\n{Path(c).name}\n✗ {e}")
    paquets.sort(key=lambda p: (p[0], p[1].name))
    cat = charger_catalogue()
    importes = 0
    for _, chemin, manifeste, fichiers, empreinte in paquets:
        dire(f"\n{chemin.name}")
        if any(s.get("empreinte") == empreinte for s in cat["seances"]):
            dire("  Déjà importé.")
            ranger_zip(chemin)
            continue
        try:
            plan = preparer(manifeste, fichiers, cat)
        except Erreur as e:
            erreurs += 1
            dire(f"✗ {e}")
            dire("  Rien n'a été modifié pour ce paquet. Renvoie ce message à Claude pour un paquet corrigé.")
            continue
        appliquer(plan, cat, empreinte)
        sauver_catalogue(cat)
        generer(cat)
        sauver_catalogue(cat)
        for r in plan["deja_la"]:
            dire(f"  déjà présent, identique : {r}")
        dire(f"  {len(plan['a_ecrire'])} fichier(s) rangé(s).")
        if commit(message_commit(plan)):
            importes += 1
        ranger_zip(chemin)
    if importes:
        pousser()
    dire(f"\nBilan : {importes} séance(s) ajoutée(s)" + (f", {erreurs} paquet(s) refusé(s)." if erreurs else "."))
    return 1 if erreurs else 0


def ranger_zip(chemin):
    try:
        if chemin.parent.resolve() == TELECHARGEMENTS.resolve():
            IMPORTES.mkdir(exist_ok=True)
            shutil.move(str(chemin), IMPORTES / chemin.name)
    except OSError:
        pass


def nom_publiable(stem, ext, date):
    s = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:70] or "fichier"
    if not re.match(r"\d{4}-\d{2}-\d{2}", s):
        s = f"{date}-{s}"
    return f"{s}.{ext.lower()}"


def titre_lisible(stem):
    t = re.sub(r"[_-]+", " ", stem).strip()
    t = re.sub(r"^\d{4} \d{2} \d{2} ", "", t)
    return (t[:1].upper() + t[1:]) if t else stem


def cmd_ajoute(args):
    depot_git()
    opts = {"--type": "entrainement", "--titre": None, "--chapitre": "", "--date": None, "--nom": None}
    reste, it = [], iter(args)
    for a in it:
        if a in opts:
            opts[a] = next(it, None)
        else:
            reste.append(a)
    if len(reste) < 2:
        raise Erreur("usage : cours ajoute R3.07 fichier.pdf [autres] [--type entrainement|fiche|exercice|divers] "
                     "[--titre \"…\"] [--chapitre \"…\"] [--date AAAA-MM-JJ] [--nom \"Nom de la ressource\"]")
    code, _ = normaliser_code(reste[0])
    type_ = opts["--type"]
    if type_ not in TYPES:
        raise Erreur(f"type « {type_} » inconnu ({', '.join(TYPES)})")
    if opts["--date"]:
        opts["--date"] = date_valide(opts["--date"], "--date")
    chemins = []
    for brut in reste[1:]:
        p = Path(brut).expanduser()
        if p.is_dir():
            chemins += sorted(x for x in p.iterdir() if x.is_file()
                              and x.suffix.lower().lstrip(".") in EXTENSIONS)
        elif p.is_file():
            chemins.append(p)
        else:
            raise Erreur(f"introuvable : {p}")
    if not chemins:
        raise Erreur("aucun fichier à ajouter")
    if opts["--titre"] and len(chemins) > 1:
        raise Erreur("--titre ne marche qu'avec un seul fichier (sinon le titre vient du nom du fichier)")
    cat = charger_catalogue()
    if opts["--nom"]:
        cat["ressources"].setdefault(code, {"nom": "", "controles": []})["nom"] = opts["--nom"].strip()
    nom_ressource = cat["ressources"].get(code, {}).get("nom", "")
    dossier = dossier_ressource(code) / TYPES[type_][0]
    deja = {sha256((RACINE / c).read_bytes()) for c, e in cat["fichiers"].items()
            if e["ressource"] == code and (RACINE / c).is_file()}
    ajoutes = 0
    for p in chemins:
        ext = p.suffix.lower().lstrip(".")
        if ext not in EXTENSIONS:
            attention(f"{p.name} : extension .{ext} refusée, ignoré")
            continue
        donnees = p.read_bytes()
        if sha256(donnees) in deja:
            dire(f"  {p.name} : déjà dans le dépôt, ignoré")
            continue
        date = opts["--date"] or dt.date.fromtimestamp(p.stat().st_mtime).isoformat()
        nom = nom_publiable(p.stem, ext, date)
        base, n = nom[:-len(ext) - 1], 2
        while (RACINE / dossier / nom).exists():
            nom = f"{base}-{n}.{ext}"
            n += 1
        manifeste = {"format": 1, "date": date, "titre": "ajout à la main",
                     "ressources": {code: nom_ressource},
                     "fichiers": [{"fichier": nom, "type": type_,
                                   "titre": opts["--titre"] or titre_lisible(p.stem),
                                   "chapitre": opts["--chapitre"] or ""}]}
        plan = preparer(manifeste, {nom: donnees}, cat)
        appliquer(plan, cat, None, seance=False)
        deja.add(sha256(donnees))
        ajoutes += 1
        dire(f"  {p.name} → {plan['entrees'][0]['chemin']} (daté du {date_fr(date)})")
    if not ajoutes:
        dire("Rien de nouveau à ajouter.")
        return 0
    sauver_catalogue(cat)
    generer(cat)
    sauver_catalogue(cat)
    if commit(f"{code} · ajout de {pluriel(ajoutes, TYPES[type_][2])}"):
        pousser()
    return 0


def cmd_fourni(args):
    depot_git()
    titre, nom_ressource, reste = None, None, []
    it = iter(args)
    for a in it:
        if a == "--titre":
            titre = next(it, None)
        elif a == "--nom":
            nom_ressource = next(it, None)
        else:
            reste.append(a)
    if len(reste) < 2:
        raise Erreur("usage : cours fourni R3.07 fichier.pdf [autres.pdf] [--titre \"CM 3 : OSPF\"] [--nom \"Nom de la ressource\"]")
    code, _ = normaliser_code(reste[0])
    cat = charger_catalogue()
    r = cat["ressources"].setdefault(code, {"nom": "", "controles": []})
    if nom_ressource:
        r["nom"] = nom_ressource.strip()
    liste = cat["fournis"].setdefault(code, [])
    ajoutes = []
    for source in map(lambda p: Path(p).expanduser(), reste[1:]):
        if not source.is_file():
            raise Erreur(f"fichier introuvable : {source}")
        cible = RACINE / dossier_ressource(code) / "fournis" / source.name
        cible.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, cible)
        t = titre if (titre and len(reste) == 2) else source.stem
        controle_perso([("titre du support", f"{t} {source.name}".encode())])
        if not any(x["fichier"] == source.name for x in liste):
            liste.append({"fichier": source.name, "titre": t, "date": dt.date.today().isoformat()})
        ajoutes.append(t)
        dire(f"  {source.name} rangé dans {cible.relative_to(RACINE).parent} (reste sur ton PC)")
    sauver_catalogue(cat)
    generer(cat)
    sauver_catalogue(cat)
    if commit(f"{code} · supports des profs listés : {', '.join(ajoutes)}"):
        pousser()
    return 0


def cmd_verifie():
    depot_git()
    probleme = False
    suivis = [p for p in git("ls-files", "-z").stdout.split("\0") if p]
    fuite = [p for p in suivis if "/fournis/" in p]
    if fuite:
        probleme = True
        dire("✗ Supports de profs suivis par Git (ils seraient publiés) :")
        for p in fuite:
            attention(p)
    elements = []
    for p in suivis:
        chemin = RACINE / p
        if chemin.is_file():
            if chemin.stat().st_size > LIMITE_CONSEIL:
                attention(f"{p} fait {chemin.stat().st_size // MO} Mo")
            elements.append((p, chemin.read_bytes()))
    bloquants, avert = scanner(elements)
    for b in bloquants:
        probleme = True
        dire(f"✗ {b}")
    for a in avert:
        attention(a)
    cat = charger_catalogue()
    for chemin in cat["fichiers"]:
        if not (RACINE / chemin).exists():
            attention(f"cité dans catalogue.json mais absent : {chemin}")
    dire("✗ Problème à corriger avant d'envoyer." if probleme
         else f"OK : {len(suivis)} fichiers suivis, aucune info perso trouvée, aucun support de prof publié.")
    return 1 if probleme else 0


def main(argv):
    args = []
    for a in argv:
        if a == "--sans-push":
            OPTIONS["sans_push"] = True
        elif a == "--oui":
            OPTIONS["oui"] = True
        else:
            args.append(a)
    try:
        if args and args[0] in ("aide", "-h", "--help"):
            dire(__doc__.strip())
            return 0
        if args and args[0] == "ajoute":
            return cmd_ajoute(args[1:])
        if args and args[0] == "fourni":
            return cmd_fourni(args[1:])
        if args and args[0] == "sommaire":
            cat = charger_catalogue()
            generer(cat)
            sauver_catalogue(cat)
            dire("Sommaires à jour.")
            return 0
        if args and args[0] == "verifie":
            return cmd_verifie()
        return cmd_importer(args)
    except Erreur as e:
        dire(f"✗ {e}")
        return 1
    except KeyboardInterrupt:
        dire("\nInterrompu.")
        return 130


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
