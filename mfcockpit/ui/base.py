"""Base commune aux onglets : zone scrollable + helper de section thémée."""
import customtkinter as ctk

from . import theme


class ThemedScroll(ctk.CTkScrollableFrame):
    """CTkScrollableFrame transparent, scrollbar violette, espacement régulier."""

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent",
                         scrollbar_button_color=theme.C["card_border"],
                         scrollbar_button_hover_color=theme.C["accent_dk"])
        self.app = app
        self.cfg = app.config_store
        self._a_replier = []
        self._derniere_largeur = 0
        # `add="+"` est IMPÉRATIF : sans lui, ce bind remplace celui que
        # CTkScrollableFrame pose sur <Configure> pour recalculer sa
        # `scrollregion`. Elle reste alors vide et la molette ne fait plus
        # rien — le panneau paraît figé.
        self.bind("<Configure>", self._sur_redimension, add="+")

    def _section(self, title, subtitle=None):
        return theme.section(self, title, subtitle)

    def replier(self, label, marge=56):
        """Fait suivre la largeur de la fenêtre à un label multiligne.

        `wraplength` est en pixels : figé, il coupe le texte dès que la fenêtre
        rétrécit. On le recalcule donc à chaque redimensionnement — c'est ce qui
        permet de poser des phrases entières dans les cartes sans jamais les
        tronquer.
        """
        self._a_replier.append((label, marge))
        if self._derniere_largeur:
            self._appliquer(label, marge, self._derniere_largeur)
        return label

    @staticmethod
    def _appliquer(label, marge, largeur):
        try:
            label.configure(wraplength=max(140, largeur - marge))
        except Exception:
            pass

    def _sur_redimension(self, event=None):
        largeur = event.width if event is not None else self.winfo_width()
        if largeur <= 1 or abs(largeur - self._derniere_largeur) < 6:
            return
        self._derniere_largeur = largeur
        for label, marge in self._a_replier:
            self._appliquer(label, marge, largeur)
