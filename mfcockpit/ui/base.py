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

    def _section(self, title, subtitle=None):
        return theme.section(self, title, subtitle)
