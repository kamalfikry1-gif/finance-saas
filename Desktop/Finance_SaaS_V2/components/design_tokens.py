"""
components/design_tokens.py — Source de vérité unique pour le design system.

Thème : Dark Blue-Teal — Inspiré Revolut/Stripe.
Philosophie : Bleu nuit profond + accents néon teal/vert pour les chiffres
              positifs et les CTAs. Lisibilité des chiffres avant tout.

Règle absolue :
    Aucune couleur, taille ou ombre ne doit être hardcodée ailleurs.
    Tout passe par ce fichier. Pour changer le thème → modifier ici uniquement.
"""


class T:
    """Design Tokens — Dark Blue-Teal Fintech Theme."""

    # ── Couleurs principales ───────────────────────────────────────────────────
    PRIMARY     = "#06b6d4"              # Teal cyan — CTA, liens, accent principal
    PRIMARY_DIM = "#0891b2"              # Teal foncé — hover
    PRIMARY_GLO = "rgba(6,182,212,0.14)" # Halo teal (ombres, focus ring)

    SUCCESS     = "#00e5a0"              # Neon vert-teal — chiffres positifs, revenus
    SUCCESS_DIM = "#00b87f"              # Vert foncé — hover success
    SUCCESS_GLO = "rgba(0,229,160,0.12)"

    WARNING     = "#f59e0b"              # Amber — attention, projection limite
    WARNING_DIM = "#d97706"
    WARNING_GLO = "rgba(245,158,11,0.12)"

    DANGER      = "#f43f5e"              # Rose-rouge — dépassement, crash, erreur
    DANGER_DIM  = "#e11d48"
    DANGER_GLO  = "rgba(244,63,94,0.12)"

    BLUE        = "#3b82f6"              # Bleu — usage secondaire, info
    PURPLE      = "#8b5cf6"              # Violet — gradient avatar assistant

    # ── Couleurs de fond — Bleu nuit profond ─────────────────────────────────
    BG_PAGE     = "#060b18"              # Fond page principal — navy quasi-noir
    BG_SIDEBAR  = "#080d1e"              # Fond sidebar — légèrement plus clair
    BG_CARD     = "#0d1528"              # Fond carte — +1 niveau de clarté
    BG_CARD_ALT = "#111d38"              # Fond carte au survol / expanders
    BG_INPUT    = "#0a1220"              # Fond champs de saisie
    BG_OVERLAY  = "#0d1830"             # Fond overlay (bot bubble, sections)

    # ── Couleurs de texte ──────────────────────────────────────────────────────
    TEXT_HIGH   = "#e8f1ff"              # Texte principal — légèrement bleuté
    TEXT_MED    = "#7a9bc4"              # Texte secondaire — bleu-gris moyen
    TEXT_LOW    = "#3d5a80"              # Texte discret — bleu-gris dim
    TEXT_MUTED  = "#1e3050"             # Texte très discret — séparateurs

    # ── Bordures ───────────────────────────────────────────────────────────────
    BORDER      = "#142038"              # Bordure standard — 1px subtile
    BORDER_MED  = "#1c3050"             # Bordure visible — mise en valeur
    BORDER_GLOW = "rgba(6,182,212,0.3)" # Bordure teal — hover/focus

    # ── Thèmes nœuds de l'arbre de décision ──────────────────────────────────
    THEME_A      = PRIMARY              # 🔍 Analyse — Teal
    THEME_A_BG   = PRIMARY_GLO
    THEME_B      = SUCCESS              # 🎯 Budget — Vert néon
    THEME_B_BG   = SUCCESS_GLO
    THEME_C      = WARNING              # 🔮 Simulateur — Amber
    THEME_C_BG   = WARNING_GLO

    # ── Typographie ────────────────────────────────────────────────────────────
    FONT_XS  = "10px"
    FONT_SM  = "11px"
    FONT_MD  = "13px"
    FONT_LG  = "15px"
    FONT_XL  = "22px"
    FONT_XXL = "44px"

    WEIGHT_NORMAL = "400"
    WEIGHT_SEMI   = "600"
    WEIGHT_BOLD   = "700"
    WEIGHT_BLACK  = "900"

    # ── Rayons ─────────────────────────────────────────────────────────────────
    RADIUS_SM   = "8px"
    RADIUS_MD   = "12px"
    RADIUS_LG   = "16px"
    RADIUS_XL   = "20px"
    RADIUS_PILL = "99px"

    # ── Ombres ─────────────────────────────────────────────────────────────────
    SHADOW_CARD    = "0 4px 24px rgba(0,0,0,0.5)"
    SHADOW_PRIMARY = "0 4px 24px rgba(6,182,212,0.2)"
    SHADOW_SUCCESS = "0 4px 20px rgba(0,229,160,0.18)"

    # ── Transitions ────────────────────────────────────────────────────────────
    TRANSITION = "all 0.18s cubic-bezier(0.4,0,0.2,1)"

    # ── Palette catégories (graphiques) ───────────────────────────────────────
    CAT_PALETTE = [
        "#06b6d4",  # Teal
        "#00e5a0",  # Vert néon
        "#f59e0b",  # Amber
        "#f43f5e",  # Rose
        "#3b82f6",  # Bleu
        "#8b5cf6",  # Violet
        "#f97316",  # Orange
        "#14b8a6",  # Teal vert
        "#a78bfa",  # Lavande
        "#34d399",  # Emeraude
    ]


def css_variables() -> str:
    """
    Retourne le bloc :root{} CSS à injecter via inject_css().
    Source unique — toutes les valeurs viennent de T.
    """
    return f"""
:root {{
    --primary:      {T.PRIMARY};
    --primary-dim:  {T.PRIMARY_DIM};
    --primary-glo:  {T.PRIMARY_GLO};
    --success:      {T.SUCCESS};
    --success-dim:  {T.SUCCESS_DIM};
    --success-glo:  {T.SUCCESS_GLO};
    --warning:      {T.WARNING};
    --warning-dim:  {T.WARNING_DIM};
    --warning-glo:  {T.WARNING_GLO};
    --danger:       {T.DANGER};
    --danger-dim:   {T.DANGER_DIM};
    --danger-glo:   {T.DANGER_GLO};
    --blue:         {T.BLUE};

    --bg-page:      {T.BG_PAGE};
    --bg-sidebar:   {T.BG_SIDEBAR};
    --bg-card:      {T.BG_CARD};
    --bg-card-alt:  {T.BG_CARD_ALT};
    --bg-input:     {T.BG_INPUT};
    --bg-overlay:   {T.BG_OVERLAY};

    --text-high:    {T.TEXT_HIGH};
    --text-med:     {T.TEXT_MED};
    --text-low:     {T.TEXT_LOW};
    --text-muted:   {T.TEXT_MUTED};

    --border:       {T.BORDER};
    --border-med:   {T.BORDER_MED};
    --border-glow:  {T.BORDER_GLOW};

    --radius-sm:    {T.RADIUS_SM};
    --radius-md:    {T.RADIUS_MD};
    --radius-lg:    {T.RADIUS_LG};
    --radius-xl:    {T.RADIUS_XL};
    --radius-pill:  {T.RADIUS_PILL};

    --shadow-card:    {T.SHADOW_CARD};
    --shadow-primary: {T.SHADOW_PRIMARY};
    --transition:     {T.TRANSITION};
}}
"""
